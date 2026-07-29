import torch
import torch.nn as nn
import torch.nn.functional as F
import math
import json
from collections import Counter


class BPETokenizer:
    def __init__(self, vocab_size=2048):
        self.vocab_size = vocab_size
        self.merges = {}
        self.vocab = {}
        self.inverse_vocab = {}
        self.special_tokens = {'<PAD>': 0, '<BOS>': 1, '<EOS>': 2}
        self.num_special = 3

    def train(self, texts):
        text = '\n'.join(texts[:10000])
        data = [b + self.num_special for b in text.encode('utf-8')]
        ids = data[:]
        num_merges = min(self.vocab_size - 256 - self.num_special, 1024)

        for step in range(num_merges):
            pair_counts = Counter()
            for i in range(len(ids) - 1):
                pair_counts[(ids[i], ids[i+1])] += 1
            if not pair_counts:
                break
            best = pair_counts.most_common(1)[0][0]
            new_id = 256 + self.num_special + step
            self.merges[best] = new_id
            new_ids = []
            j = 0
            while j < len(ids):
                if j < len(ids) - 1 and (ids[j], ids[j+1]) == best:
                    new_ids.append(new_id)
                    j += 2
                else:
                    new_ids.append(ids[j])
                    j += 1
            ids = new_ids
        self._build_vocab()

    def _build_vocab(self):
        self.inverse_vocab = {v: k for k, v in self.vocab.items()}
        self._token_to_bytes = {}
        for i in range(256):
            self._token_to_bytes[i + self.num_special] = bytes([i])
        for pair, idx in self.merges.items():
            a, b = pair
            ba = self._token_to_bytes.get(a, b'')
            bb = self._token_to_bytes.get(b, b'')
            self._token_to_bytes[idx] = ba + bb

    _merge_cache = {}

    def encode(self, text, add_special=True):
        raw = text.encode('utf-8')
        raw_tuple = tuple(raw)
        if raw_tuple in self._merge_cache:
            result = list(self._merge_cache[raw_tuple])
        else:
            ids = [b + self.num_special for b in raw]
            changed = True
            while changed:
                changed = False
                best_priority = float('inf')
                best_pair = None
                for i in range(len(ids) - 1):
                    pair = (ids[i], ids[i+1])
                    priority = self.merges.get(pair)
                    if priority is not None and priority < best_priority:
                        best_priority = priority
                        best_pair = pair
                if best_pair is not None:
                    changed = True
                    new_id = self.merges[best_pair]
                    new_ids = []
                    j = 0
                    while j < len(ids):
                        if j < len(ids) - 1 and (ids[j], ids[j+1]) == best_pair:
                            new_ids.append(new_id)
                            j += 2
                        else:
                            new_ids.append(ids[j])
                            j += 1
                    ids = new_ids
            result = ids
            self._merge_cache[raw_tuple] = tuple(result)
        if add_special:
            return [self.special_tokens['<BOS>']] + result + [self.special_tokens['<EOS>']]
        return result[:]

    def decode(self, ids):
        tokens = []
        for i in ids:
            if i in self._token_to_bytes:
                tokens.append(self._token_to_bytes[i])
            elif i not in self.special_tokens.values():
                tokens.append(bytes([max(0, i - self.num_special)]))
        return b''.join(tokens).decode('utf-8', errors='replace')

    def save(self, path):
        with open(path, 'w') as f:
            json.dump({
                'vocab_size': self.vocab_size,
                'merges': {f'{k[0]},{k[1]}': v for k, v in self.merges.items()},
            }, f)

    @classmethod
    def load(cls, path):
        with open(path) as f:
            data = json.load(f)
        tok = cls(vocab_size=data['vocab_size'])
        tok.merges = {tuple(map(int, k.split(','))): v for k, v in data['merges'].items()}
        tok._build_vocab()
        return tok


Tokenizer = BPETokenizer


class RMSNorm(nn.Module):
    def __init__(self, dim, eps=1e-6):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def forward(self, x):
        rms = torch.sqrt((x.pow(2).mean(-1, keepdim=True)) + self.eps)
        return x / rms * self.weight


def precompute_rope_freqs(dim, max_seq_len, theta=10000.0):
    inv_freq = 1.0 / (theta ** (torch.arange(0, dim, 2).float() / dim))
    positions = torch.arange(max_seq_len).float()
    freqs = torch.outer(positions, inv_freq)
    return torch.cos(freqs), torch.sin(freqs)


def apply_rope(x, cos, sin):
    d = x.shape[-1]
    x1 = x[..., :d//2]
    x2 = x[..., d//2:]
    cos = cos[:x.shape[-2], :d//2]
    sin = sin[:x.shape[-2], :d//2]
    rotated = torch.cat([x1 * cos - x2 * sin, x1 * sin + x2 * cos], dim=-1)
    return rotated.type_as(x)


class MultiHeadAttention(nn.Module):
    def __init__(self, dim, n_heads, dropout=0.1):
        super().__init__()
        self.n_heads = n_heads
        self.head_dim = dim // n_heads
        self.dim = dim
        self.q_proj = nn.Linear(dim, dim, bias=False)
        self.k_proj = nn.Linear(dim, dim, bias=False)
        self.v_proj = nn.Linear(dim, dim, bias=False)
        self.out_proj = nn.Linear(dim, dim, bias=False)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, cos, sin, mask=None, past_kv=None, use_cache=False, cache_offset=0):
        B, T, C = x.shape
        q = self.q_proj(x).view(B, T, self.n_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(B, T, self.n_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(B, T, self.n_heads, self.head_dim).transpose(1, 2)
        offset = cache_offset if past_kv is not None else 0
        pos_k = torch.arange(offset, offset + k.shape[-2], device=k.device)
        pos_q = torch.arange(offset, offset + q.shape[-2], device=q.device)
        k = apply_rope(k, cos[pos_k], sin[pos_k])
        q = apply_rope(q, cos[pos_q], sin[pos_q])
        if past_kv is not None:
            pk, pv = past_kv
            k = torch.cat([pk, k], dim=-2)
            v = torch.cat([pv, v], dim=-2)
        present_kv = (k, v) if use_cache else None
        attn = (q @ k.transpose(-2, -1)) / math.sqrt(self.head_dim)
        if mask is not None:
            attn = attn.masked_fill(mask == 0, float('-inf'))
        attn = F.softmax(attn, dim=-1)
        attn = self.dropout(attn)
        out = (attn @ v).transpose(1, 2).contiguous().view(B, T, C)
        return self.out_proj(out), present_kv


class SwiGLU(nn.Module):
    def __init__(self, dim, hidden_mult=8/3):
        super().__init__()
        hidden_dim = int(dim * hidden_mult)
        self.w1 = nn.Linear(dim, hidden_dim, bias=False)
        self.w2 = nn.Linear(hidden_dim, dim, bias=False)
        self.w3 = nn.Linear(dim, hidden_dim, bias=False)

    def forward(self, x):
        return self.w2(F.silu(self.w1(x)) * self.w3(x))


class TransformerBlock(nn.Module):
    def __init__(self, dim, n_heads, dropout=0.1):
        super().__init__()
        self.attn = MultiHeadAttention(dim, n_heads, dropout)
        self.ffn = SwiGLU(dim)
        self.norm1 = RMSNorm(dim)
        self.norm2 = RMSNorm(dim)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, cos, sin, mask=None, past_kv=None, use_cache=False, cache_offset=0):
        attn_out, present_kv = self.attn(self.norm1(x), cos, sin, mask, past_kv, use_cache, cache_offset)
        x = x + self.dropout(attn_out)
        x = x + self.dropout(self.ffn(self.norm2(x)))
        return x, present_kv


CONFIGS = {
    'tiny':   dict(dim=128,  n_layers=4,  n_heads=4,  max_seq_len=256),
    'small':  dict(dim=256,  n_layers=6,  n_heads=8,  max_seq_len=384),
    'medium': dict(dim=384,  n_layers=8,  n_heads=12, max_seq_len=512),
    'large':  dict(dim=512,  n_layers=12, n_heads=16, max_seq_len=512),
}


class GPT(nn.Module):
    def __init__(self, vocab_size, dim=256, n_layers=6, n_heads=8, max_seq_len=384, dropout=0.1):
        super().__init__()
        self.dim = dim
        self.max_seq_len = max_seq_len
        self.vocab_size = vocab_size
        self.token_embedding = nn.Embedding(vocab_size, dim)
        self.blocks = nn.ModuleList([
            TransformerBlock(dim, n_heads, dropout) for _ in range(n_layers)
        ])
        self.norm = RMSNorm(dim)
        self.lm_head = nn.Linear(dim, vocab_size, bias=False)
        cos, sin = precompute_rope_freqs(dim // n_heads, max_seq_len * 2)
        self.register_buffer('cos', cos, persistent=False)
        self.register_buffer('sin', sin, persistent=False)
        self.apply(self._init_weights)

    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(self, idx, targets=None, past_kvs=None, use_cache=False):
        B, T = idx.shape
        if use_cache and past_kvs is not None and past_kvs[0] is not None:
            cache_len = past_kvs[0][0].shape[-2]
            total_len = cache_len + T
        else:
            cache_len = 0
            total_len = T
        cos = self.cos[:total_len].to(idx.device)
        sin = self.sin[:total_len].to(idx.device)
        x = self.token_embedding(idx)
        mask = None
        if T > 1:
            mask = torch.tril(torch.ones(T, T, device=idx.device)).view(1, 1, T, T)
        new_kvs = []
        for i, block in enumerate(self.blocks):
            past_kv = past_kvs[i] if past_kvs is not None else None
            x, present_kv = block(x, cos, sin, mask, past_kv, use_cache, cache_len)
            new_kvs.append(present_kv)
        x = self.norm(x)
        logits = self.lm_head(x)
        loss = None
        if targets is not None:
            loss = F.cross_entropy(logits.view(-1, self.vocab_size), targets.view(-1), ignore_index=0)
        return logits, loss, new_kvs if use_cache else None

    @torch.no_grad()
    def generate(self, idx, max_new_tokens, temperature=0.8, top_k=40, use_cache=True):
        eos_id = 2
        if use_cache:
            logits, _, past_kvs = self.forward(idx, use_cache=True)
            idx_next = self._sample(logits[:, -1, :], temperature, top_k)
            idx = torch.cat((idx, idx_next), dim=1)
            for _ in range(max_new_tokens - 1):
                logits, _, past_kvs = self.forward(idx_next, past_kvs=past_kvs, use_cache=True)
                idx_next = self._sample(logits[:, -1, :], temperature, top_k)
                idx = torch.cat((idx, idx_next), dim=1)
                if idx_next.item() == eos_id:
                    break
        else:
            for _ in range(max_new_tokens):
                idx_cond = idx[:, -self.max_seq_len:]
                logits, _, _ = self.forward(idx_cond, use_cache=False)
                idx_next = self._sample(logits[:, -1, :], temperature, top_k)
                idx = torch.cat((idx, idx_next), dim=1)
                if idx_next.item() == eos_id:
                    break
        return idx

    def _sample(self, logits, temperature, top_k):
        logits = logits / temperature
        if top_k is not None:
            values, _ = torch.topk(logits, top_k)
            logits[logits < values[:, -1:]] = float('-inf')
        probs = F.softmax(logits, dim=-1)
        return torch.multinomial(probs, num_samples=1)

    @torch.no_grad()
    def generate_text(self, prompt, tokenizer, max_new=200, temperature=0.8, top_k=40, use_cache=True):
        self.eval()
        device = next(self.parameters()).device
        if not prompt:
            prompt_ids = [tokenizer.special_tokens['<BOS>']]
        else:
            prompt_ids = tokenizer.encode(prompt, add_special=True)
        x = torch.tensor([prompt_ids], device=device)
        out = self.generate(x, max_new, temperature, top_k, use_cache)
        return tokenizer.decode(out[0].tolist())
