import json
import os
import sys
import subprocess
import threading
import time
import uuid

import torch
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='web', static_url_path='')
CORS(app, resources={r"/api/*": {"origins": "*"}})

device = torch.device("cpu")
tokenizer = None
model = None
train_thread_obj = None
train_running = False
train_result = {}
extraction_in_progress = False

HERE = os.path.dirname(os.path.abspath(__file__))
MESSAGES_FILE = os.path.join(HERE, "messages.json")
MODEL_FILE = os.path.join(HERE, "model.pt")
TOKENIZER_FILE = os.path.join(HERE, "tokenizer.json")
TRAIN_CONFIG_FILE = os.path.join(HERE, "train_config.json")
FORMATTED_FILE = os.path.join(HERE, "formatted.txt")
CHECKPOINT_FILE = os.path.join(HERE, "checkpoint.pt")

train_progress = {
    'status': 'idle',
    'percent': 0,
    'epoch': 0,
    'total_epochs': 20,
    'loss': '--',
    'best_loss': '--',
    'step': 0,
    'total_steps': 0,
    'elapsed': 0,
    'eta': '--',
    'model_size': 'small',
    'messages_count': 0,
    'params': 0,
}


@app.route("/")
def index():
    return send_from_directory('web', 'index.html')


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory('web', path)


@app.route("/api/status")
def api_status():
    global train_running, extraction_in_progress
    return jsonify({
        'model_loaded': model is not None,
        'messages': _count_messages(),
        'train_running': train_running,
        'train_progress': train_progress,
        'extraction_in_progress': extraction_in_progress,
        'extractors': get_extractors_info(),
        'has_checkpoint': os.path.exists(CHECKPOINT_FILE),
        'version': '1.0.0',
    })


@app.route("/api/generate", methods=["POST"])
def api_generate():
    global model, tokenizer
    data = request.json
    prompt = data.get("prompt", "")
    temperature = data.get("temperature", 0.8)
    top_k = data.get("top_k", 40)
    max_new = data.get("max_new", 150)
    history = data.get("history", [])

    if model is None:
        return jsonify({"error": "Model not loaded. Train or load a model first."}), 400

    context = ""
    for h in history[-4:]:
        context += f'{h["role"]}: {h["content"]}\n'
    context += f'user: {prompt}\nassistant: '

    text = model.generate_text(context, tokenizer, max_new, temperature, top_k, use_cache=True)
    for b in ['<BOS>', '<EOS>', '<PAD>']:
        text = text.replace(b, '')
    if 'assistant: ' in text:
        response = text.split('assistant: ')[-1]
    else:
        response = text
    if response.startswith('user: ') or response.startswith('assistant: '):
        response = response.split(': ', 1)[-1]
    for marker in ['\nuser: ', '\nassistant: ']:
        if marker in response:
            response = response.split(marker)[0]

    return jsonify({"text": response.strip()})


@app.route("/api/add_message", methods=["POST"])
def api_add_message():
    data = request.json
    role = data.get("role", "user")
    text = data.get("text", "")

    messages = _load_messages()
    messages.append({
        "role": role,
        "text": text,
        "timestamp": time.time(),
        "sender": "app",
        "service": "app",
    })
    _save_messages(messages)
    _append_to_training_files(text)

    return jsonify({"ok": True, "total": len(messages)})


@app.route("/api/extract", methods=["POST"])
def api_extract():
    global extraction_in_progress
    data = request.json or {}
    source = data.get("source", None)
    max_msgs = data.get("max_messages", None)

    def do_extract():
        global extraction_in_progress
        extraction_in_progress = True
        try:
            os.makedirs(HERE, exist_ok=True)
            existing = _load_messages()
            if source and source != 'all':
                from extractors import extract_from
                new_msgs = extract_from(source, max_messages=max_msgs)
            else:
                from extractors import extract_all
                new_msgs, results = extract_all(max_messages=max_msgs)
            existing_ids = set()
            for m in existing:
                key = (m.get('text', ''), m.get('timestamp', ''), m.get('sender', ''))
                existing_ids.add(key)
            unique_new = []
            for m in new_msgs:
                key = (m.get('text', ''), m.get('timestamp', ''), m.get('sender', ''))
                if key not in existing_ids:
                    existing_ids.add(key)
                    unique_new.append(m)
            all_msgs = existing + unique_new
            _save_messages(all_msgs)
            _rebuild_training_files(all_msgs)
            return {'ok': True, 'new': len(unique_new), 'total': len(all_msgs)}
        except Exception as e:
            raise e
        finally:
            extraction_in_progress = False

    if data.get('sync', False):
        try:
            result = do_extract()
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        threading.Thread(target=do_extract, daemon=True).start()
        return jsonify({"ok": True, "message": "Extraction started in background"})


@app.route("/api/import", methods=["POST"])
def api_import():
    data = request.json
    source = data.get("source", "Generic Import")
    filepath = data.get("filepath", "")
    if not filepath or not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 400
    try:
        from extractors import import_file
        new_msgs = import_file(source, filepath, **data.get('options', {}))
        existing = _load_messages()
        existing_texts = set(m.get('text', '') for m in existing)
        unique = [m for m in new_msgs if m.get('text', '') not in existing_texts]
        all_msgs = existing + unique
        _save_messages(all_msgs)
        _rebuild_training_files(all_msgs)
        return jsonify({"ok": True, "new": len(unique), "total": len(all_msgs), "imported": len(new_msgs)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload_import", methods=["POST"])
def api_upload_import():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files['file']
    source = request.form.get('source', 'Generic Import')
    ext = os.path.splitext(file.filename)[1].lower()
    temp_path = os.path.join(HERE, f"_upload_{uuid.uuid4().hex}{ext}")
    file.save(temp_path)
    try:
        from extractors import import_file
        new_msgs = import_file(source, temp_path)
        existing = _load_messages()
        existing_texts = set(m.get('text', '') for m in existing)
        unique = [m for m in new_msgs if m.get('text', '') not in existing_texts]
        all_msgs = existing + unique
        _save_messages(all_msgs)
        _rebuild_training_files(all_msgs)
        return jsonify({"ok": True, "new": len(unique), "total": len(all_msgs), "imported": len(new_msgs)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.route("/api/train", methods=["POST"])
def api_train():
    global train_thread_obj, train_running
    data = request.json or {}
    action = data.get("action", "start")
    if action == "start":
        if train_running:
            return jsonify({"error": "Already training"}), 400
        if not os.path.exists(FORMATTED_FILE):
            return jsonify({"error": "No training data. Extract or import messages first."}), 400
        n_epochs = data.get("epochs", 20)
        resume = data.get("resume", False)
        model_size = data.get("model_size", "small")
        train_running = True
        train_progress['status'] = 'starting'
        train_progress['model_size'] = model_size
        train_progress['total_epochs'] = n_epochs
        def run_train():
            global train_running, train_result
            try:
                from train import train as train_fn, on_progress
                def progress_cb(event, data):
                    update_train_progress(event, data)
                on_progress(progress_cb)
                best_loss = train_fn(
                    device=torch.device("cpu"),
                    n_epochs=n_epochs, resume=resume, model_size=model_size,
                )
                train_result = {'loss': best_loss, 'error': None}
            except Exception as e:
                train_result = {'loss': None, 'error': str(e)}
                train_progress['status'] = 'error'
                train_progress['error'] = str(e)
            finally:
                train_running = False
                load_model()
        train_thread_obj = threading.Thread(target=run_train, daemon=True)
        train_thread_obj.start()
        return jsonify({"ok": True, "message": "Training started"})
    elif action == "stop":
        train_running = False
        train_progress['status'] = 'stopped'
        return jsonify({"ok": True, "message": "Training stopped"})
    elif action == "status":
        return jsonify({'running': train_running, 'progress': train_progress})
    return jsonify({"error": "Unknown action"}), 400


@app.route("/api/progress")
def api_progress():
    return jsonify({'running': train_running, 'progress': train_progress})


@app.route("/api/messages")
def api_messages():
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)
    service = request.args.get("service", None)
    messages = _load_messages()
    if service:
        messages = [m for m in messages if m.get('service') == service]
    total = len(messages)
    page = messages[offset:offset + limit]
    services = set(m.get('service') for m in messages if m.get('service'))
    stats = {
        'total': total,
        'user': sum(1 for m in messages if m['role'] == 'user'),
        'assistant': sum(1 for m in messages if m['role'] == 'assistant'),
        'services': sorted(s for s in services if s),
        'characters': sum(len(m.get('text', '')) for m in messages),
    }
    return jsonify({'messages': page, 'total': total, 'stats': stats})


@app.route("/api/export", methods=["POST"])
def api_export():
    data = request.json or {}
    fmt = data.get("format", "json")
    filepath = data.get("filepath", os.path.join(HERE, f"export_{int(time.time())}.{fmt}"))
    messages = _load_messages()
    if fmt == "json":
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(messages, f, indent=2, ensure_ascii=False)
    elif fmt == "txt":
        with open(filepath, 'w', encoding='utf-8') as f:
            for m in messages:
                f.write(m['text'] + '\n')
    elif fmt == "formatted":
        with open(filepath, 'w', encoding='utf-8') as f:
            for m in messages:
                role = 'user' if m['role'] == 'user' else 'assistant'
                f.write(f'{role}: {m["text"]}\n')
    else:
        return jsonify({"error": f"Unknown format: {fmt}"}), 400
    return jsonify({"ok": True, "filepath": filepath, "count": len(messages)})


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        data = request.json or {}
        config_path = os.path.join(HERE, "server_config.json")
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)
        return jsonify({"ok": True})
    config_path = os.path.join(HERE, "server_config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return jsonify(json.load(f))
    return jsonify({})


def update_train_progress(event, data):
    global train_progress
    if event == 'status':
        train_progress['status'] = data
    elif event == 'device':
        train_progress['device'] = data
    elif event == 'config':
        train_progress.update({
            'model_size': data.get('model_size', train_progress['model_size']),
            'n_layers': data.get('n_layers'),
            'dim': data.get('dim'),
        })
    elif event == 'messages':
        train_progress['messages_count'] = data
    elif event == 'tokenizer':
        train_progress['vocab_size'] = data
    elif event == 'params':
        train_progress['params'] = data
    elif event == 'step':
        train_progress.update({
            'percent': data.get('percent', 0),
            'epoch': data.get('epoch', 0),
            'step': data.get('step', 0),
            'total_steps': data.get('total_steps', 0),
            'loss': str(data.get('loss', '--')),
        })
    elif event == 'epoch':
        epochs_left = data.get('total_epochs', 0) - data.get('epoch', 0)
        ep_duration = data.get('elapsed', 0)
        eta_seconds = epochs_left * ep_duration if epochs_left > 0 and ep_duration > 0 else 0
        eta_str = _fmt_time(eta_seconds) if eta_seconds > 0 else '--'
        train_progress.update({
            'percent': round(data.get('epoch', 0) / max(data.get('total_epochs', 1), 1) * 100, 1),
            'epoch': data.get('epoch', 0),
            'total_epochs': data.get('total_epochs', 0),
            'loss': str(data.get('loss', '--')),
            'best_loss': str(data.get('best_loss', '--')),
            'lr': data.get('lr', ''),
            'elapsed': data.get('elapsed', 0),
            'eta': eta_str,
            'status': 'training',
        })
    elif event == 'complete':
        train_progress.update({
            'status': 'complete',
            'best_loss': str(data.get('best_loss', '--')),
            'percent': 100,
        })
    elif event == 'error':
        train_progress.update({
            'status': 'error',
            'error': str(data),
        })


def _fmt_time(seconds):
    seconds = int(seconds)
    if seconds < 0:
        return '--'
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f'{h}h {m}m'
    if m > 0:
        return f'{m}m {s}s'
    return f'{s}s'


def get_extractors_info():
    try:
        from extractors import list_available
        return list_available()
    except:
        return []


def _load_messages():
    if os.path.exists(MESSAGES_FILE):
        with open(MESSAGES_FILE, encoding='utf-8') as f:
            return json.load(f)
    return []


def _save_messages(messages):
    with open(MESSAGES_FILE, 'w', encoding='utf-8') as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)


def _append_to_training_files(text):
    with open(os.path.join(HERE, "messages.txt"), "a", encoding='utf-8') as f:
        f.write(text.strip() + "\n")
    with open(os.path.join(HERE, "flat.txt"), "a", encoding='utf-8') as f:
        f.write(text)


def _rebuild_training_files(messages):
    texts = [m["text"] for m in messages]
    with open(os.path.join(HERE, "messages.txt"), "w", encoding='utf-8') as f:
        for t in texts:
            f.write(t.strip() + "\n")
    with open(os.path.join(HERE, "flat.txt"), "w", encoding='utf-8') as f:
        for t in texts:
            f.write(t)
    with open(os.path.join(HERE, "flat_formatted.txt"), "w", encoding='utf-8') as f:
        for m in messages:
            role = 'user' if m['role'] == 'user' else 'assistant'
            f.write(f'{role}: {m["text"]}\n')
    _build_conversation_format(messages)


def _build_conversation_format(messages):
    lines = []
    for m in messages:
        role = 'user' if m['role'] == 'user' else 'assistant'
        text = m['text'].replace('\n', ' ').replace('\r', ' ')
        lines.append(f'{role}: {text}')
    with open(FORMATTED_FILE, 'w', encoding='utf-8') as f:
        for l in lines:
            f.write(l + '\n')
    convos = _build_conversations(messages)
    with open(os.path.join(HERE, "conversations.json"), 'w', encoding='utf-8') as f:
        json.dump(convos, f, indent=2, ensure_ascii=False)


def _build_conversations(messages, max_turns=20):
    conversations = []
    current = []
    for msg in messages:
        role = "assistant" if msg["role"] == "assistant" else "user"
        current.append({"role": role, "content": msg["text"]})
        if len(current) >= max_turns * 2:
            conversations.append(current)
            current = []
    if current:
        conversations.append(current)
    return conversations


def _count_messages():
    try:
        msgs = _load_messages()
        return len(msgs)
    except:
        return 0


def load_model():
    global tokenizer, model
    try:
        tokenizer_path = TOKENIZER_FILE
        model_path = MODEL_FILE
        if not os.path.exists(tokenizer_path):
            print("No tokenizer found")
            return
        from model import BPETokenizer, GPT
        tokenizer = BPETokenizer.load(tokenizer_path)
        model = GPT(
            vocab_size=tokenizer.vocab_size,
            dim=256, n_layers=6, n_heads=8,
            max_seq_len=384, dropout=0.15,
        ).to(device)
        if os.path.exists(model_path):
            model.load_state_dict(torch.load(model_path, map_location=device))
            model.eval()
            print(f"Model loaded from {model_path}")
        else:
            print("No model found. Train first.")
    except Exception as e:
        print(f"Error loading model: {e}")
        tokenizer = None
        model = None


def auto_extract_imessage():
    try:
        from extractors.imessage import is_available, extract
        if is_available():
            existing = _load_messages()
            existing_texts = set(m.get('text', '') for m in existing)
            new_msgs = extract()
            unique = [m for m in new_msgs if m.get('text', '') not in existing_texts]
            if unique:
                all_msgs = existing + unique
                _save_messages(all_msgs)
                _rebuild_training_files(all_msgs)
                print(f"  Auto-extracted {len(unique)} iMessage(s)")
            else:
                print(f"  iMessage: {len(existing)} already loaded")
        else:
            print(f"  iMessage not available on this system")
    except Exception as e:
        print(f"  iMessage auto-extract: {e}")


def open_browser():
    import webbrowser
    try:
        webbrowser.open('http://127.0.0.1:5050')
    except:
        pass


def main():
    global training_log
    port = int(os.environ.get("PORT", 5050))
    host = os.environ.get("HOST", "0.0.0.0")

    AUTO_EXTRACT_FLAG = os.path.join(HERE, ".auto_extracted")
    if not os.path.exists(AUTO_EXTRACT_FLAG):
        auto_extract_imessage()
        try:
            with open(AUTO_EXTRACT_FLAG, 'w') as f:
                f.write('1')
        except:
            pass

    load_model()
    if not os.path.exists(MESSAGES_FILE):
        _save_messages([])

    auto_open = os.environ.get("OPEN_BROWSER", "1") == "1"
    if auto_open:
        threading.Timer(1.5, open_browser).start()

    print(f"\n")
    print(f"  🧠  Universal Chat AI")
    print(f"  ─────────────────────")
    print(f"  ✅  Open:  http://127.0.0.1:{port}")
    print(f"  📱  Phone: http://YOUR_IP:{port}")
    print(f"  ⏹  Quit:  Ctrl+C in this window\n")

    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
