import json
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import os
import time
import sys
import threading

from model import BPETokenizer, GPT

CKPT_FILE = "checkpoint.pt"
CONFIG_FILE = "train_config.json"
MODEL_FILE = "model.pt"
FORMATTED_FILE = "formatted.txt"
TOKENIZER_FILE = "tokenizer.json"


class ChunkedDataset(Dataset):
    def __init__(self, texts, tokenizer, seq_len=256):
        self.seq_len = seq_len
        all_ids = []
        for t in texts:
            ids = tokenizer.encode(t.strip())
            all_ids.extend(ids)
        self.data = torch.tensor(all_ids, dtype=torch.long)
        self.num_chunks = len(self.data) // seq_len
        self.data = self.data[:self.num_chunks * seq_len]

    def __len__(self):
        return max(0, self.num_chunks - 1)

    def __getitem__(self, idx):
        start = idx * self.seq_len
        return self.data[start:start + self.seq_len], self.data[start + 1:start + self.seq_len + 1]


progress_listeners = []


def on_progress(callback):
    progress_listeners.append(callback)


def emit_progress(event, data=None):
    for cb in progress_listeners:
        try:
            cb(event, data)
        except Exception:
            pass


def build_formatted(messages_json_path, output_path):
    with open(messages_json_path, encoding='utf-8') as f:
        msgs = json.load(f)
    lines = []
    for m in msgs:
        role = 'user' if m['role'] == 'user' else 'assistant'
        text = m['text'].replace('\n', ' ').replace('\r', ' ')
        lines.append(f'{role}: {text}')
    with open(output_path, 'w', encoding='utf-8') as f:
        for l in lines:
            f.write(l + '\n')
    return len(lines)


def train(device=None, n_epochs=None, resume=False, model_size='small', callbacks=None):
    if callbacks:
        on_progress(callbacks)

    emit_progress('status', 'Initializing training...')

    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    emit_progress('device', str(device))

    if n_epochs is None:
        n_epochs = 20

    cfg = CONFIGS.get(model_size, CONFIGS['small'])
    dim = cfg['dim']
    n_layers = cfg['n_layers']
    n_heads = cfg['n_heads']
    max_seq_len = cfg['max_seq_len']
    dropout = 0.15
    batch_size = 16
    lr = 3e-4
    max_lr = 5e-3

    emit_progress('config', {
        'model_size': model_size,
        'dim': dim,
        'n_layers': n_layers,
        'n_heads': n_heads,
        'max_seq_len': max_seq_len,
        'batch_size': batch_size,
        'n_epochs': n_epochs,
    })

    resume_epoch = 0
    best_loss = float('inf')

    if resume and os.path.exists(CKPT_FILE):
        emit_progress('status', 'Resuming from checkpoint...')
        ckpt = torch.load(CKPT_FILE, map_location=device, weights_only=False)
        resume_epoch = ckpt["epoch"] + 1
        best_loss = ckpt.get("best_loss", float('inf'))
        n_epochs = ckpt.get("n_epochs", n_epochs)
        tokenizer = BPETokenizer.load(TOKENIZER_FILE)

        with open(FORMATTED_FILE, encoding='utf-8') as f:
            texts = [line.strip() for line in f if line.strip()]
        emit_progress('messages', len(texts))

        dataset = ChunkedDataset(texts, tokenizer, max_seq_len)
        dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=0, drop_last=True)
        total_steps = len(dataloader) * n_epochs

        model = GPT(
            vocab_size=tokenizer.vocab_size,
            dim=dim, n_layers=n_layers, n_heads=n_heads,
            max_seq_len=max_seq_len, dropout=dropout,
        ).to(device)
        model.load_state_dict(ckpt["model"])
        optimizer = torch.optim.AdamW(model.parameters(), lr=lr, betas=(0.9, 0.95), weight_decay=0.1)
        optimizer.load_state_dict(ckpt["optimizer"])
        scheduler = torch.optim.lr_scheduler.OneCycleLR(
            optimizer, max_lr=max_lr, total_steps=total_steps,
            pct_start=0.1, anneal_strategy='cos',
        )
        scheduler.load_state_dict(ckpt["scheduler"])

        emit_progress('status', f'Resumed at epoch {resume_epoch+1}/{n_epochs}')
    else:
        emit_progress('status', 'Preparing data and tokenizer...')

        with open(FORMATTED_FILE, encoding='utf-8') as f:
            texts = [line.strip() for line in f if line.strip()]
        emit_progress('messages', len(texts))

        tokenizer = BPETokenizer(vocab_size=2048)
        tokenizer.train(texts)
        tokenizer.save(TOKENIZER_FILE)
        emit_progress('tokenizer', tokenizer.vocab_size)

        dataset = ChunkedDataset(texts, tokenizer, max_seq_len)
        dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=0, drop_last=True)
        total_steps = len(dataloader) * n_epochs

        model = GPT(
            vocab_size=tokenizer.vocab_size,
            dim=dim, n_layers=n_layers, n_heads=n_heads,
            max_seq_len=max_seq_len, dropout=dropout,
        ).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=lr, betas=(0.9, 0.95), weight_decay=0.1)
        scheduler = torch.optim.lr_scheduler.OneCycleLR(
            optimizer, max_lr=max_lr, total_steps=total_steps,
            pct_start=0.1, anneal_strategy='cos',
        )

    total_params = sum(p.numel() for p in model.parameters())
    emit_progress('params', total_params)
    emit_progress('status', f'Training: {n_epochs} epochs x {len(dataloader)} steps')

    for epoch in range(resume_epoch, n_epochs):
        model.train()
        total_loss = 0
        start = time.time()

        for batch_idx, (x, y) in enumerate(dataloader):
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            _, loss, _ = model(x, y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            total_loss += loss.item()

            if batch_idx % 10 == 0 or batch_idx == len(dataloader) - 1:
                avg_l = total_loss / (batch_idx + 1)
                pct = ((epoch - resume_epoch) * len(dataloader) + batch_idx + 1) / \
                       ((n_epochs - resume_epoch) * len(dataloader)) * 100
                emit_progress('step', {
                    'percent': round(pct, 1),
                    'epoch': epoch + 1,
                    'total_epochs': n_epochs,
                    'step': batch_idx + 1,
                    'total_steps': len(dataloader),
                    'loss': round(avg_l, 4),
                })

        avg_loss = total_loss / len(dataloader)
        lr_val = scheduler.get_last_lr()[0]
        elapsed = time.time() - start

        saved = False
        if avg_loss < best_loss:
            best_loss = avg_loss
            torch.save(model.state_dict(), MODEL_FILE)
            saved = True

        torch.save({
            "epoch": epoch,
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "best_loss": best_loss,
            "n_epochs": n_epochs,
        }, CKPT_FILE)

        emit_progress('epoch', {
            'epoch': epoch + 1,
            'total_epochs': n_epochs,
            'loss': round(avg_loss, 4),
            'best_loss': round(best_loss, 4),
            'lr': f'{lr_val:.2e}',
            'elapsed': round(elapsed, 1),
            'saved': saved,
        })

    emit_progress('complete', {'best_loss': round(best_loss, 4)})

    if os.path.exists(CKPT_FILE):
        os.remove(CKPT_FILE)

    return best_loss


CONFIGS = {
    'tiny':   dict(dim=128,  n_layers=4,  n_heads=4,  max_seq_len=256),
    'small':  dict(dim=256,  n_layers=6,  n_heads=8,  max_seq_len=384),
    'medium': dict(dim=384,  n_layers=8,  n_heads=12, max_seq_len=512),
    'large':  dict(dim=512,  n_layers=12, n_heads=16, max_seq_len=512),
}


def train_in_thread(device=None, n_epochs=20, resume=False, model_size='small', result_holder=None):
    def callback(event, data):
        if callbacks:
            for cb in callbacks:
                try:
                    cb(event, data)
                except Exception:
                    pass

    local_callbacks = []

    def on_progress_local(cb):
        local_callbacks.append(cb)

    import train as train_module
    train_module.on_progress = on_progress_local

    best_loss = None
    error = None
    try:
        best_loss = train(device=device, n_epochs=n_epochs, resume=resume, model_size=model_size)
    except Exception as e:
        error = str(e)
        import traceback
        traceback.print_exc()

    if result_holder is not None:
        result_holder['loss'] = best_loss
        result_holder['error'] = error


callbacks = []
