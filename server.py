import json, os, sys, subprocess, threading, time, uuid, shutil, io, zipfile, webbrowser
import torch
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS

app = Flask(__name__, static_folder='web', static_url_path='')
CORS(app, resources={r"/api/*": {"origins": "*"}})

device = torch.device("cpu")
tokenizer = None
model = None
train_thread_obj = None
train_running = False
extraction_in_progress = False
phone_detected = None
phone_checking = False

HERE = os.path.dirname(os.path.abspath(__file__))
MESSAGES_FILE = os.path.join(HERE, "messages.json")
MODEL_FILE = os.path.join(HERE, "model.pt")
TOKENIZER_FILE = os.path.join(HERE, "tokenizer.json")
FORMATTED_FILE = os.path.join(HERE, "formatted.txt")

train_progress = {'status': 'idle', 'percent': 0, 'epoch': 0, 'total_epochs': 20, 'loss': '--', 'best_loss': '--', 'elapsed': 0, 'eta': '--', 'model_size': 'small', 'messages_count': 0}

# ── Phone auto-detection ──────────────────────────────────
def check_for_phone():
    global phone_detected, phone_checking
    if phone_checking: return
    phone_checking = True
    try:
        from extractors import detect_devices
        phone_detected = detect_devices()
    except: pass
    finally: phone_checking = False

def phone_watcher():
    while True:
        check_for_phone()
        time.sleep(5)

threading.Thread(target=phone_watcher, daemon=True).start()

# ── Routes ────────────────────────────────────────────────
@app.route("/")
def index(): return send_from_directory('web', 'index.html')

@app.route("/<path:path>")
def static_files(path): return send_from_directory('web', path)

@app.route("/api/status")
def api_status():
    return jsonify({
        'model_loaded': model is not None,
        'messages': _count_messages(), 'train_running': train_running,
        'train_progress': train_progress, 'extraction_in_progress': extraction_in_progress,
        'version': '1.1.0', 'phone_detected': phone_detected,
    })

@app.route("/api/generate", methods=["POST"])
def api_generate():
    global model, tokenizer
    data = request.json
    if model is None:
        return jsonify({"error": "Train or load a model first."}), 400
    prompt = data.get("prompt", "")
    temp = data.get("temperature", 0.8)
    max_new = data.get("max_new", 150)
    history = data.get("history", [])

    context = ""
    for h in history[-4:]:
        context += f'{h["role"]}: {h["content"]}\n'
    context += f'user: {prompt}\nassistant: '

    text = model.generate_text(context, tokenizer, max_new, temp, top_k=40, use_cache=True)
    for b in ['<BOS>', '<EOS>', '<PAD>']: text = text.replace(b, '')
    if 'assistant: ' in text: response = text.split('assistant: ')[-1]
    else: response = text
    for marker in ['\nuser: ', '\nassistant: ']:
        if marker in response: response = response.split(marker)[0]
    return jsonify({"text": response.strip()})

@app.route("/api/extract", methods=["POST"])
def api_extract():
    global extraction_in_progress
    data = request.json or {}

    def do():
        global extraction_in_progress
        extraction_in_progress = True
        try:
            new_msgs = []
            source = data.get("source")
            if source and source in ('iPhone (USB)', 'Android (USB)'):
                from extractors import extract_from
                new_msgs = extract_from(source, udid=data.get("udid"),
                    selected_apps=data.get("apps"), max_messages=data.get("max_messages"))
            elif source:
                from extractors import extract_from
                new_msgs = extract_from(source, max_messages=data.get("max_messages"))
            else:
                from extractors import extract_all
                new_msgs, _ = extract_all(max_messages=data.get("max_messages"))
            existing = _load_messages()
            seen = set((m.get('text',''), m.get('timestamp',''), m.get('sender','')) for m in existing)
            unique = [m for m in new_msgs if (m.get('text',''), m.get('timestamp',''), m.get('sender','')) not in seen]
            all_msgs = existing + unique
            _save_messages(all_msgs)
            _rebuild_training_files(all_msgs)
            return {'ok': True, 'new': len(unique), 'total': len(all_msgs)}
        except Exception as e: raise e
        finally: extraction_in_progress = False

    if data.get('sync'):
        try: return jsonify(do())
        except Exception as e: return jsonify({"error": str(e)}), 500
    else:
        threading.Thread(target=do, daemon=True).start()
        return jsonify({"ok": True, "message": "Extracting..."})

@app.route("/api/upload_import", methods=["POST"])
def api_upload_import():
    if 'file' not in request.files: return jsonify({"error": "No file"}), 400
    file = request.files['file']
    source = request.form.get('source', 'Generic Import')
    ext = os.path.splitext(file.filename)[1].lower()
    temp = os.path.join(HERE, f"_upload_{uuid.uuid4().hex}{ext}")
    file.save(temp)
    try:
        from extractors import import_file
        new_msgs = import_file(source, temp)
        existing = _load_messages()
        seen = set(m.get('text','') for m in existing)
        unique = [m for m in new_msgs if m.get('text','') not in seen]
        all_msgs = existing + unique
        _save_messages(all_msgs); _rebuild_training_files(all_msgs)
        return jsonify({"ok": True, "new": len(unique), "total": len(all_msgs), "imported": len(new_msgs)})
    except Exception as e: return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(temp): os.remove(temp)

@app.route("/api/train", methods=["POST"])
def api_train():
    global train_thread_obj, train_running
    data = request.json or {}
    action = data.get("action", "start")
    if action == "start":
        if train_running: return jsonify({"error": "Already training"}), 400
        if not os.path.exists(FORMATTED_FILE): return jsonify({"error": "No data. Extract messages first."}), 400
        train_running = True; train_progress['status'] = 'starting'
        train_progress.update(epochs=data.get("epochs",20), model_size=data.get("model_size","small"))
        def run():
            global train_running
            try:
                from train import train as train_fn, on_progress as reg
                def cb(e,d): update_train_progress(e,d)
                reg(cb); train_fn(device=torch.device("cpu"), n_epochs=data.get("epochs",20), model_size=data.get("model_size","small"))
            except Exception as e: train_progress.update(status='error', error=str(e))
            finally: train_running = False; load_model()
        train_thread_obj = threading.Thread(target=run, daemon=True); train_thread_obj.start()
        return jsonify({"ok": True})
    elif action == "stop":
        train_running = False; train_progress['status'] = 'stopped'
        return jsonify({"ok": True})

@app.route("/api/progress")
def api_progress(): return jsonify({'running': train_running, 'progress': train_progress})

@app.route("/api/messages")
def api_messages():
    msgs = _load_messages()
    stats = {'total': len(msgs), 'user': sum(1 for m in msgs if m['role']=='user'),
             'assistant': sum(1 for m in msgs if m['role']=='assistant')}
    return jsonify({'total': len(msgs), 'stats': stats})

@app.route("/api/model/export", methods=["POST"])
def api_model_export():
    if not os.path.exists(MODEL_FILE) and not os.path.exists(TOKENIZER_FILE):
        return jsonify({"error": "No model trained yet"}), 400
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        if os.path.exists(MODEL_FILE): z.write(MODEL_FILE, "model.pt")
        if os.path.exists(TOKENIZER_FILE): z.write(TOKENIZER_FILE, "tokenizer.json")
        if os.path.exists(FORMATTED_FILE): z.write(FORMATTED_FILE, "formatted.txt")
        if request.json and request.json.get("include_messages") and os.path.exists(MESSAGES_FILE):
            z.write(MESSAGES_FILE, "messages.json")
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name="chat-ai-model.zip")

@app.route("/api/model/import", methods=["POST"])
def api_model_import():
    if 'file' not in request.files: return jsonify({"error": "No file"}), 400
    temp = os.path.join(HERE, f"_model_{uuid.uuid4().hex}.zip")
    request.files['file'].save(temp)
    try:
        with zipfile.ZipFile(temp, 'r') as z:
            if 'model.pt' not in z.namelist() and 'tokenizer.json' not in z.namelist():
                return jsonify({"error": "No model files in zip"}), 400
            z.extractall(HERE)
        load_model()
        return jsonify({"ok": True})
    except Exception as e: return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(temp): os.remove(temp)

# ── Helpers ───────────────────────────────────────────────
def update_train_progress(event, data):
    global train_progress
    if event == 'status': train_progress['status'] = data
    elif event == 'config': train_progress.update(model_size=data.get('model_size', train_progress['model_size']))
    elif event == 'messages': train_progress['messages_count'] = data
    elif event == 'step': train_progress.update(percent=data.get('percent',0), epoch=data.get('epoch',0), loss=str(data.get('loss','--')))
    elif event == 'epoch':
        el = data.get('elapsed',0); left = data.get('total_epochs',0)-data.get('epoch',0)
        train_progress.update(percent=round(data['epoch']/max(data['total_epochs'],1)*100,1), epoch=data['epoch'],
            total_epochs=data['total_epochs'], loss=str(data.get('loss','--')), best_loss=str(data.get('best_loss','--')),
            elapsed=el, eta=f'{int(left*el//60)}m' if left*el>0 else'--', status='training')
    elif event == 'complete': train_progress.update(status='complete', percent=100, best_loss=str(data.get('best_loss','--')))
    elif event == 'error': train_progress.update(status='error', error=str(data))

def _load_messages():
    if os.path.exists(MESSAGES_FILE):
        with open(MESSAGES_FILE, encoding='utf-8') as f: return json.load(f)
    return []
def _save_messages(m):
    with open(MESSAGES_FILE, 'w', encoding='utf-8') as f: json.dump(m, f, indent=2, ensure_ascii=False)
def _clean_text(t):
    if not t: return ''
    import re, unicodedata
    t = unicodedata.normalize('NFKC', str(t))
    t = re.sub(r'&amp;', '&', t); t = re.sub(r'&lt;', '<', t); t = re.sub(r'&gt;', '>', t)
    t = re.sub(r'&quot;', '"', t); t = re.sub(r'&#\d+;', ' ', t); t = re.sub(r'&[a-zA-Z]+;', ' ', t)
    t = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', t)
    t = re.sub(r'\r\n?', '\n', t); t = re.sub(r'[ \t]+\n', '\n', t)
    t = re.sub(r'\n{3,}', '\n\n', t); t = t.strip()
    return t

def _rebuild_training_files(messages):
    with open(FORMATTED_FILE, 'w', encoding='utf-8') as f:
        for m in messages:
            text = _clean_text(m.get('text', ''))
            if not text: continue
            f.write(f'{"user" if m["role"]=="user" else "assistant"}: {text}\n')
def _count_messages():
    try: return len(_load_messages())
    except: return 0

def load_model():
    global tokenizer, model
    try:
        if not os.path.exists(TOKENIZER_FILE): return
        from model import BPETokenizer, GPT
        tokenizer = BPETokenizer.load(TOKENIZER_FILE)
        model = GPT(vocab_size=tokenizer.vocab_size, dim=256, n_layers=6, n_heads=8, max_seq_len=384, dropout=0.15).to(device)
        if os.path.exists(MODEL_FILE):
            model.load_state_dict(torch.load(MODEL_FILE, map_location=device)); model.eval()
    except Exception as e: print(f"Model load error: {e}"); tokenizer=None; model=None

def auto_extract_imessage():
    try:
        from extractors.imessage import is_available, extract
        if is_available():
            existing = _load_messages(); seen = set(m.get('text','') for m in existing)
            new = [m for m in extract() if m.get('text','') not in seen]
            if new: _save_messages(existing+new); _rebuild_training_files(existing+new)
    except: pass

def open_browser():
    try: webbrowser.open('http://127.0.0.1:5050')
    except: pass

def main():
    port = int(os.environ.get("PORT", 5050))
    flag = os.path.join(HERE, ".auto_extracted")
    if not os.path.exists(flag):
        auto_extract_imessage()
        try: open(flag,'w').close()
        except: pass
    load_model()
    if not os.path.exists(MESSAGES_FILE): _save_messages([])
    if os.environ.get("OPEN_BROWSER","1")=="1": threading.Timer(1.5, open_browser).start()
    print(f"\n  🧠  Universal Chat AI\n  ─────────────────────\n  ✅  Open: http://127.0.0.1:{port}\n  ⏹  Quit: Ctrl+C\n")
    app.run(host=os.environ.get("HOST","0.0.0.0"), port=port, debug=False, threaded=True)

if __name__ == "__main__": main()
