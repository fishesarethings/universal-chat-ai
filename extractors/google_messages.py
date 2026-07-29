import json
import os
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

name = "Google Messages"
description = "Import messages from Google Takeout (JSON) or SMS Backup & Restore (XML/JSON)"
platforms = ["all"]

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


def is_available():
    return True


def extract():
    raise NotImplementedError("Google Messages has no live DB. Use import_file() with a Takeout export.")


def import_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    fname = os.path.basename(filepath).lower()

    if ext == '.json' and ('takeout' in fname or 'messages' in fname):
        return _import_takeout_json(filepath)
    elif ext == '.json' and 'backup' in fname:
        return _import_sms_backup_json(filepath)
    elif ext == '.xml':
        return _import_sms_backup_xml(filepath)
    elif ext == '.csv':
        return _import_csv(filepath)
    elif ext == '.json':
        return _import_takeout_json(filepath)
    else:
        raise ValueError(f"Unsupported format. Use Google Takeout JSON or SMS Backup & Restore XML/JSON.")


def _import_takeout_json(filepath):
    with open(filepath, encoding='utf-8') as f:
        data = json.load(f)

    messages = []
    convos = data.get('messages', data)

    if isinstance(convos, dict):
        for conv_id, msgs in convos.items():
            for m in msgs:
                msg = _parse_message(m)
                if msg:
                    messages.append(msg)
    elif isinstance(convos, list):
        for m in convos:
            if isinstance(m, dict) and 'text' in m:
                msg = _parse_message(m)
                if msg:
                    messages.append(msg)
            elif isinstance(m, dict):
                for conv_id, msgs in m.items():
                    for mm in msgs:
                        msg = _parse_message(mm)
                        if msg:
                            messages.append(msg)

    return messages


def _parse_message(m):
    if not isinstance(m, dict):
        return None
    text = m.get('text') or m.get('message') or ''
    if not text or not isinstance(text, str) or not text.strip():
        return None

    is_from_me = m.get('is_from_me', m.get('fromMe', m.get('type', '')) in ('sent', 'outgoing', '1'))
    role = "assistant" if is_from_me else "user"

    ts = m.get('timestamp', m.get('date', m.get('datetime', None)))
    if ts and isinstance(ts, (int, float)):
        try:
            ts = datetime.fromtimestamp(ts / 1000).isoformat()
        except:
            ts = None
    elif ts and isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace('Z', '+00:00')).isoformat()
        except:
            pass

    return {
        "role": role,
        "text": text.strip(),
        "timestamp": ts,
        "sender": m.get('sender', m.get('address', m.get('from', None))),
        "service": "Google Messages",
    }


def _import_sms_backup_xml(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()
    messages = []

    for sms in root.findall('sms'):
        text = sms.get('body', '')
        if not text.strip():
            continue
        type_ = sms.get('type', '1')
        role = "assistant" if type_ == '2' else "user"
        ts_str = sms.get('readable_date', sms.get('date', ''))
        messages.append({
            "role": role,
            "text": text.strip(),
            "timestamp": ts_str or None,
            "sender": sms.get('address', sms.get('contact_name', None)),
            "service": "Google Messages",
        })

    return messages


def _import_sms_backup_json(filepath):
    with open(filepath, encoding='utf-8') as f:
        data = json.load(f)

    messages = []
    for sms in data if isinstance(data, list) else data.get('sms', []):
        text = sms.get('body', '')
        if not text.strip():
            continue
        type_ = sms.get('type', '1')
        role = "assistant" if str(type_) == '2' else "user"
        messages.append({
            "role": role,
            "text": text.strip(),
            "timestamp": sms.get('readable_date', sms.get('date', None)),
            "sender": sms.get('address', sms.get('contact_name', None)),
            "service": "Google Messages",
        })

    return messages


def _import_csv(filepath):
    if not HAS_PANDAS:
        raise ImportError("pandas is required for CSV import: pip install pandas")
    df = pd.read_csv(filepath)
    messages = []

    text_col = next((c for c in df.columns if c.lower() in ('text', 'body', 'message', 'content')), None)
    type_col = next((c for c in df.columns if c.lower() in ('type', 'direction', 'is_from_me')), None)
    date_col = next((c for c in df.columns if c.lower() in ('date', 'timestamp', 'datetime', 'time')), None)
    sender_col = next((c for c in df.columns if c.lower() in ('sender', 'from', 'address', 'phone', 'contact')), None)

    if not text_col:
        raise ValueError("CSV must have a 'text', 'body', or 'message' column")

    for _, row in df.iterrows():
        text = str(row[text_col])
        if not text.strip():
            continue
        if type_col:
            val = str(row[type_col]).lower()
            role = "assistant" if val in ('sent', 'outgoing', '2', 'true', '1', 'me') else "user"
        else:
            role = "user"
        ts = str(row[date_col]) if date_col and pd.notna(row[date_col]) else None
        sender = str(row[sender_col]) if sender_col and pd.notna(row[sender_col]) else None
        messages.append({
            "role": role,
            "text": text.strip(),
            "timestamp": ts,
            "sender": sender,
            "service": "Google Messages",
        })

    return messages
