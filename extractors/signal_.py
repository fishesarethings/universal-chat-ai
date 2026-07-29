import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

name = "Signal"
description = "Import Signal messages from Signal Desktop DB (macOS/Linux) or JSON export"
platforms = ["macOS", "Linux"]

SIGNAL_DB_MAC = os.path.expanduser("~/Library/Application Support/Signal/sql/db.sqlite")
SIGNAL_DB_LINUX = os.path.expanduser("~/.config/Signal/sql/db.sqlite")
SIGNAL_DB_WIN = os.path.expandvars(r"%APPDATA%\Signal\sql\db.sqlite")


def is_available():
    return os.path.exists(SIGNAL_DB_MAC) or os.path.exists(SIGNAL_DB_LINUX)


def _get_db_path():
    for p in [SIGNAL_DB_MAC, SIGNAL_DB_LINUX, SIGNAL_DB_WIN]:
        if os.path.exists(p):
            return p
    return None


def extract(max_messages=None):
    db_path = _get_db_path()
    if not db_path:
        raise RuntimeError(
            "Signal Desktop DB not found. Install Signal Desktop, log in, "
            "and let it sync before extracting. "
            "Alternatively, use import_file() with a JSON export."
        )

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = conn.cursor()

    query = """
    SELECT
        m.body,
        m.type,
        m.sent_at,
        c.name as conversation_name,
        m.source
    FROM messages m
    LEFT JOIN conversations c ON m.conversationId = c.id
    WHERE m.body IS NOT NULL AND m.body != ''
    ORDER BY m.sent_at ASC
    """
    if max_messages:
        query = query.replace("ORDER BY m.sent_at ASC", "ORDER BY m.sent_at DESC LIMIT ?")
        cur.execute(query, (max_messages,))
    else:
        cur.execute(query)

    rows = cur.fetchall()
    conn.close()

    messages = []
    for body, msg_type, sent_at, conv_name, source in rows:
        role = "assistant" if msg_type in ('outgoing', 1, '1') else "user"
        ts = None
        if sent_at and sent_at > 0:
            try:
                ts = datetime.fromtimestamp(sent_at / 1000, tz=timezone.utc).isoformat()
            except:
                pass
        messages.append({
            "role": role,
            "text": body.strip(),
            "timestamp": ts,
            "sender": source or conv_name or "unknown",
            "service": "Signal",
        })

    return messages


def import_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()

    if ext == '.json':
        with open(filepath, encoding='utf-8') as f:
            data = json.load(f)

        messages = []
        items = data if isinstance(data, list) else data.get('messages', data.get('conversations', [data]))
        for item in items:
            if isinstance(item, dict):
                msgs = item.get('messages', [item])
                for m in msgs:
                    parsed = _parse_message(m)
                    if parsed:
                        messages.append(parsed)

        return messages
    else:
        raise ValueError("Unsupported format. Use Signal JSON export.")


def _parse_message(m):
    text = m.get('body', m.get('text', m.get('message', '')))
    if not text or not isinstance(text, str) or not text.strip():
        return None

    role = "user"
    type_val = str(m.get('type', m.get('direction', ''))).lower()
    if type_val in ('outgoing', 'sent', '1', 'true', 'from_me'):
        role = "assistant"

    ts = m.get('sent_at', m.get('timestamp', m.get('date', None)))
    if ts and isinstance(ts, (int, float)) and ts > 0:
        try:
            ts = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
        except:
            ts = None

    return {
        "role": role,
        "text": text.strip(),
        "timestamp": ts,
        "sender": m.get('source', m.get('sender', m.get('from', None))),
        "service": "Signal",
    }
