import json
import csv
import os
import glob

name = "Generic Import"
description = "Import messages from any JSON, CSV, or TXT file with flexible column mapping"
platforms = ["all"]

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


def is_available():
    return True


def extract():
    raise NotImplementedError("Generic has no live extraction. Use import_file()")


def import_file(filepath, text_field=None, role_field=None, timestamp_field=None,
                sender_field=None, service_name="Generic", role_map=None):
    ext = os.path.splitext(filepath)[1].lower()

    if ext == '.json':
        return _import_json(filepath, text_field, role_field, timestamp_field, sender_field, service_name, role_map)
    elif ext == '.csv':
        return _import_csv(filepath, text_field, role_field, timestamp_field, sender_field, service_name, role_map)
    elif ext == '.txt':
        return _import_txt(filepath, service_name)
    elif ext == '.ndjson' or ext == '.jsonl':
        return _import_jsonl(filepath, text_field, role_field, timestamp_field, sender_field, service_name, role_map)
    else:
        raise ValueError(f"Unsupported format: {ext}. Use .json, .csv, .txt, .ndjson")


def import_directory(dirpath, pattern='*', **kwargs):
    messages = []
    paths = glob.glob(os.path.join(dirpath, pattern))
    for p in sorted(paths):
        if os.path.isfile(p):
            try:
                msgs = import_file(p, **kwargs)
                messages.extend(msgs)
            except Exception as e:
                print(f"  Skipping {os.path.basename(p)}: {e}")
    return messages


def _guess_role(val, role_map=None):
    if not val:
        return "user"
    val_str = str(val).lower().strip()
    if role_map:
        for role_key, mapped_role in role_map.items():
            if val_str == str(role_key).lower():
                return mapped_role
    if val_str in ('assistant', 'sent', 'outgoing', 'true', '1', 'from_me', 'me', '2'):
        return "assistant"
    return "user"


def _import_json(filepath, text_field, role_field, timestamp_field, sender_field, service_name, role_map):
    with open(filepath, encoding='utf-8') as f:
        data = json.load(f)

    items = data if isinstance(data, list) else _find_list(data)
    if not items:
        items = [data]

    return _process_items(items, text_field, role_field, timestamp_field, sender_field, service_name, role_map)


def _import_jsonl(filepath, text_field, role_field, timestamp_field, sender_field, service_name, role_map):
    items = []
    with open(filepath, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except:
                    pass
    return _process_items(items, text_field, role_field, timestamp_field, sender_field, service_name, role_map)


def _import_csv(filepath, text_field, role_field, timestamp_field, sender_field, service_name, role_map):
    with open(filepath, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        items = list(reader)

    text_field = text_field or _auto_detect_field(items, ['text', 'body', 'message', 'content', 'msg'])
    role_field = role_field or _auto_detect_field(items, ['role', 'type', 'direction', 'is_from_me'])
    timestamp_field = timestamp_field or _auto_detect_field(items, ['timestamp', 'date', 'datetime', 'time', 'created_at'])
    sender_field = sender_field or _auto_detect_field(items, ['sender', 'from', 'author', 'user', 'name', 'handle', 'address'])

    return _process_items(items, text_field, role_field, timestamp_field, sender_field, service_name, role_map)


def _import_txt(filepath, service_name):
    messages = []
    with open(filepath, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                messages.append({
                    "role": "user",
                    "text": line,
                    "timestamp": None,
                    "sender": None,
                    "service": service_name,
                })
    return messages


def _auto_detect_field(items, candidates):
    if not items:
        return None
    keys = set()
    for item in items[:100]:
        if isinstance(item, dict):
            keys.update(item.keys())
    keys_lower = {k.lower(): k for k in keys}
    for candidate in candidates:
        if candidate in keys_lower:
            return keys_lower[candidate]
        if candidate in keys:
            return candidate
    return None


def _find_list(data):
    if isinstance(data, list):
        return data
    for key, val in data.items():
        if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
            return val
    return []


def _process_items(items, text_field, role_field, timestamp_field, sender_field, service_name, role_map):
    messages = []
    text_field = text_field or _auto_detect_field(items, ['text', 'body', 'message', 'content', 'msg', 'transcript'])

    for item in items:
        if not isinstance(item, dict):
            continue

        if text_field:
            text = str(item.get(text_field, ''))
        else:
            vals = [str(v) for v in item.values() if isinstance(v, str) and len(v) > 10]
            text = vals[0] if vals else ''
        if not text.strip():
            continue

        role = "user"
        if role_field:
            role = _guess_role(item.get(role_field, ''), role_map)

        ts = str(item.get(timestamp_field, '')) if timestamp_field else None
        sender = str(item.get(sender_field, '')) if sender_field else None
        if sender and sender.lower() in ('none', 'null', ''):
            sender = None

        messages.append({
            "role": role,
            "text": text.strip(),
            "timestamp": ts if ts and ts.lower() not in ('none', 'null', '') else None,
            "sender": sender,
            "service": service_name,
        })

    return messages
