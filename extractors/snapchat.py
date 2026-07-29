import json
import os
import zipfile
import re
from datetime import datetime

name = "Snapchat"
description = "Import Snapchat messages from Snapchat My Data download (JSON files in zip)"
platforms = ["all"]


def is_available():
    return True


def extract():
    raise NotImplementedError(
        "Snapchat has no direct DB access. Use import_file() with a Snapchat My Data .zip"
    )


def import_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()

    if ext == '.zip':
        return _import_zip(filepath)
    elif ext == '.json':
        return _import_json(filepath)
    elif ext == '.html':
        return _import_html(filepath)
    else:
        raise ValueError("Unsupported format. Use Snapchat My Data .zip")


def _parse_snapchat_timestamp(ts_str):
    if not ts_str:
        return None
    ts_str = str(ts_str).strip()
    try:
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S',
                    '%Y-%m-%d %I:%M:%S %p', '%b %d, %Y %I:%M:%S %p',
                    '%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%S%z']:
            try:
                return datetime.strptime(ts_str, fmt).isoformat()
            except:
                pass
        try:
            return datetime.fromtimestamp(int(ts_str) / 1000).isoformat()
        except:
            pass
    except:
        pass
    return ts_str


def _import_zip(filepath):
    messages = []
    with zipfile.ZipFile(filepath, 'r') as z:
        for name in z.namelist():
            lower = name.lower()
            if 'chat' in lower and name.endswith('.json'):
                with z.open(name) as f:
                    try:
                        data = json.loads(f.read().decode('utf-8'))
                        parsed = _parse_chat_data(data)
                        messages.extend(parsed)
                    except:
                        pass
            elif name.endswith('.json') and ('message' in lower or 'conversation' in lower):
                with z.open(name) as f:
                    try:
                        data = json.loads(f.read().decode('utf-8'))
                        parsed = _parse_chat_data(data)
                        messages.extend(parsed)
                    except:
                        pass
    return messages


def _import_json(filepath):
    with open(filepath, encoding='utf-8') as f:
        data = json.load(f)
    return _parse_chat_data(data)


def _import_html(filepath):
    with open(filepath, encoding='utf-8') as f:
        content = f.read()

    messages = []
    patterns = [
        (r'<div class="chatMessage[^"]*">.*?<span class="sender">(.*?)</span>.*?<span class="message">(.*?)</span>.*?<span class="timestamp">(.*?)</span>', re.DOTALL),
        (r'<p class="[^"]*from[^"]*">(.*?)</p>\s*<p class="[^"]*text[^"]*">(.*?)</p>\s*<p class="[^"]*time[^"]*">(.*?)</p>', re.DOTALL),
    ]

    for pattern, flags in patterns:
        for match in re.finditer(pattern, content, flags):
            sender = match.group(1).strip()
            text = match.group(2).strip()
            ts = match.group(3).strip()
            if text and sender:
                messages.append({
                    "role": "user" if 'you' not in sender.lower() else "assistant",
                    "text": text,
                    "timestamp": _parse_snapchat_timestamp(ts),
                    "sender": sender,
                    "service": "Snapchat",
                })

    return messages


def _parse_chat_data(data):
    messages = []

    if isinstance(data, list):
        for item in data:
            parsed = _parse_single(item)
            if parsed:
                messages.append(parsed)
    elif isinstance(data, dict):
        for key in ('chat_history', 'conversations', 'messages', 'Saved Media', 'Chat'):
            items = data.get(key, data if key == 'Chat' else None)
            if items and items is not data:
                if isinstance(items, list):
                    for item in items:
                        parsed = _parse_single(item)
                        if parsed:
                            messages.append(parsed)
                break

    return messages


def _parse_single(item):
    if not isinstance(item, dict):
        return None

    text = item.get('Text', item.get('text', item.get('message', item.get('Content', ''))))
    if not text or not isinstance(text, str) or not text.strip():
        return None

    sender = item.get('From', item.get('from', item.get('sender', item.get('Sender', 'unknown'))))

    is_me = False
    me_fields = ['is_from_me', 'IsFromMe', 'isFromMe', 'from_me']
    for f in me_fields:
        val = item.get(f, None)
        if val is not None:
            is_me = bool(val) if isinstance(val, (bool, int)) else str(val).lower() == 'true'
            break

    if not is_me and sender:
        sender_lower = str(sender).lower()
        if sender_lower in ('me', 'you', 'i'):
            is_me = True

    role = "assistant" if is_me else "user"

    ts = item.get('Timestamp', item.get('timestamp', item.get('Date', item.get('date', None))))
    if ts:
        ts = _parse_snapchat_timestamp(ts)

    return {
        "role": role,
        "text": text.strip(),
        "timestamp": ts,
        "sender": str(sender) if sender else None,
        "service": "Snapchat",
    }
