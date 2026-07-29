import json
import os
import zipfile
from datetime import datetime

name = "Discord"
description = "Import Discord Data Package (request from Discord privacy settings, download as JSON)"
platforms = ["all"]


def is_available():
    return True


def extract():
    raise NotImplementedError("Discord has no local DB. Use import_file() with a Discord Data Package export.")


def import_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()

    if ext == '.zip':
        return _import_zip(filepath)
    elif ext == '.json':
        return _import_json(filepath)
    elif os.path.isdir(filepath):
        return _import_directory(filepath)
    else:
        raise ValueError(f"Unsupported format. Use a Discord Data Package .zip, .json, or directory.")


def _import_zip(filepath):
    messages = []
    with zipfile.ZipFile(filepath, 'r') as z:
        for name in z.namelist():
            if name.endswith('.json') and ('messages' in name.lower() or 'channel' in name.lower()):
                with z.open(name) as f:
                    try:
                        data = json.loads(f.read().decode('utf-8'))
                        messages.extend(_parse_messages(data))
                    except:
                        pass
    return messages


def _import_json(filepath):
    with open(filepath, encoding='utf-8') as f:
        data = json.load(f)
    return _parse_messages(data)


def _import_directory(filepath):
    messages = []
    for root, dirs, files in os.walk(filepath):
        for fname in files:
            if fname.endswith('.json'):
                try:
                    with open(os.path.join(root, fname), encoding='utf-8') as f:
                        data = json.load(f)
                    messages.extend(_parse_messages(data))
                except:
                    pass
    return messages


def _parse_messages(data):
    messages = []

    if isinstance(data, list):
        for msg in data:
            parsed = _parse_single(msg)
            if parsed:
                messages.append(parsed)
    elif isinstance(data, dict):
        channel_msgs = data.get('messages', data.get('channel', data))
        if isinstance(channel_msgs, list):
            for msg in channel_msgs:
                parsed = _parse_single(msg)
                if parsed:
                    messages.append(parsed)
        else:
            for key, msgs in data.items():
                if isinstance(msgs, list):
                    for msg in msgs:
                        parsed = _parse_single(msg)
                        if parsed:
                            messages.append(parsed)

    return messages


def _parse_single(msg):
    if not isinstance(msg, dict):
        return None

    content = msg.get('content', msg.get('text', ''))
    if not content or not isinstance(content, str) or not content.strip():
        msg_type = msg.get('type', '')
        if msg_type not in ('0', 0, 'Default', ''):
            return None
        return None

    author = msg.get('author', msg.get('sender', {}))
    if isinstance(author, dict):
        sender = author.get('name', author.get('username', author.get('id', 'unknown')))
    else:
        sender = str(author) if author else 'unknown'

    is_self = msg.get('is_from_me', False)
    if isinstance(author, dict):
        is_self = is_self or author.get('is_self', False)
    if isinstance(is_self, str):
        is_self = is_self.lower() == 'true'

    role = "assistant" if is_self else "user"

    ts = msg.get('timestamp', msg.get('date', msg.get('time', None)))
    if ts and isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace('Z', '+00:00')).isoformat()
        except:
            pass
    elif ts and isinstance(ts, (int, float)):
        try:
            ts = datetime.fromtimestamp(ts / 1000).isoformat()
        except:
            ts = None

    return {
        "role": role,
        "text": content.strip(),
        "timestamp": ts,
        "sender": sender,
        "service": "Discord",
    }
