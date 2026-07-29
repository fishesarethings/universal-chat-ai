import re
import json
import os
import zipfile
from datetime import datetime

name = "WhatsApp"
description = "Import WhatsApp chat exports (.txt from chat export feature) or JSON"
platforms = ["all"]


def is_available():
    return True


def extract():
    raise NotImplementedError(
        "WhatsApp has no direct DB access. Use import_file() with a chat export .txt"
    )


def import_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()

    if ext == '.txt':
        return _import_txt(filepath)
    elif ext == '.zip':
        return _import_zip(filepath)
    elif ext == '.json':
        return _import_json(filepath)
    else:
        raise ValueError("Unsupported format. Use WhatsApp chat export .txt")


def _import_txt(filepath):
    with open(filepath, encoding='utf-8') as f:
        content = f.read()

    messages = []
    lines = content.strip().split('\n')

    wa_date_pattern = re.compile(
        r'^\[?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}),?\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*(AM|PM)?\]?\s*'
        r'[-~]?\s*([^:]+):\s*(.+)'
    )
    alt_pattern = re.compile(
        r'^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)\s*[-–]+\s*([^:]+):\s(.+)'
    )
    system_pattern = re.compile(
        r'^\[?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}),?\s*(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)\]?\s*[-~]?\s*(.+)'
    )

    for line in lines:
        line = line.strip()
        if not line:
            continue

        m = wa_date_pattern.match(line)
        if not m:
            m = alt_pattern.match(line)

        if m:
            date_str = m.group(1)
            time_str = m.group(2)
            ampm = m.group(3) if m.lastindex >= 3 else ''
            sender = m.group(4) if m.lastindex >= 4 else ''
            text = m.group(5) if m.lastindex >= 5 else ''

            if not sender or not text:
                continue
            if text.lower().startswith('<media ') or text == '':
                continue

            ts = _parse_datetime(date_str, time_str, ampm)
            is_me = 'you' in sender.lower() or 'me' in sender.lower()

            messages.append({
                "role": "assistant" if is_me else "user",
                "text": text.strip(),
                "timestamp": ts,
                "sender": sender.strip(),
                "service": "WhatsApp",
            })
        else:
            sm = system_pattern.match(line)
            if sm:
                continue
            else:
                if messages:
                    messages[-1]["text"] += "\n" + line

    return messages


def _parse_datetime(date_str, time_str, ampm):
    try:
        if '/' in date_str:
            parts = date_str.split('/')
        elif '-' in date_str:
            parts = date_str.split('-')
        else:
            return None
        if len(parts) == 3:
            if len(parts[2]) == 2:
                parts[2] = '20' + parts[2]
            if ampm:
                dt_str = f"{parts[0]}/{parts[1]}/{parts[2]} {time_str} {ampm}"
            else:
                dt_str = f"{parts[0]}/{parts[1]}/{parts[2]} {time_str}"
            for fmt in ['%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y %I:%M %p',
                        '%d/%m/%Y %I:%M:%S %p', '%d/%m/%Y %I:%M %p',
                        '%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M',
                        '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M']:
                try:
                    return datetime.strptime(dt_str.strip(), fmt).isoformat()
                except:
                    pass
    except:
        pass
    return None


def _import_zip(filepath):
    messages = []
    with zipfile.ZipFile(filepath, 'r') as z:
        for name in z.namelist():
            if name.endswith('.txt'):
                with z.open(name) as f:
                    content = f.read().decode('utf-8', errors='replace')
                temp_path = f"/tmp/_wa_{os.getpid()}.txt"
                with open(temp_path, 'w', encoding='utf-8') as tf:
                    tf.write(content)
                try:
                    messages.extend(_import_txt(temp_path))
                finally:
                    os.remove(temp_path)
    return messages


def _import_json(filepath):
    with open(filepath, encoding='utf-8') as f:
        data = json.load(f)
    messages = []
    items = data if isinstance(data, list) else data.get('messages', [data])
    for m in items:
        text = m.get('text', m.get('body', m.get('message', '')))
        if not text or not text.strip():
            continue
        sender = m.get('sender', m.get('from', m.get('author', 'unknown')))
        is_me = str(m.get('type', '')).lower() in ('outgoing', 'sent', '1', 'true')
        messages.append({
            "role": "assistant" if is_me else "user",
            "text": text.strip(),
            "timestamp": m.get('timestamp', m.get('date', None)),
            "sender": sender,
            "service": "WhatsApp",
        })
    return messages
