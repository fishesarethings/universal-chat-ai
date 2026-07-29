import sqlite3
import os
import sys
import json
from datetime import datetime, timedelta

name = "iMessage"
description = "Extract messages from macOS iMessage chat.db"
platforms = ["macOS"]

DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")


def is_available():
    return sys.platform == "darwin" and os.path.exists(DB_PATH)


def mac_absolute_to_datetime(mac_abs_time):
    if mac_abs_time is None or mac_abs_time == 0:
        return None
    return datetime(2001, 1, 1) + timedelta(seconds=mac_abs_time / 1_000_000_000)


def extract(max_messages=None):
    if not is_available():
        raise RuntimeError("iMessage database not found. macOS only.")

    conn = sqlite3.connect(DB_PATH)
    conn.text_factory = str
    cur = conn.cursor()

    query = """
    SELECT
        m.text,
        m.is_from_me,
        m.date,
        m.service,
        h.id as sender_id
    FROM message m
    LEFT JOIN handle h ON m.handle_id = h.ROWID
    WHERE m.text IS NOT NULL AND m.text != ''
    ORDER BY m.date ASC
    """
    if max_messages:
        query = query.replace("ORDER BY m.date ASC", "ORDER BY m.date DESC LIMIT ?")
        cur.execute(query, (max_messages,))
    else:
        cur.execute(query)

    rows = cur.fetchall()
    conn.close()

    messages = []
    for text, is_from_me, date, service, sender_id in rows:
        dt = mac_absolute_to_datetime(date)
        ts = dt.isoformat() if dt else None
        role = "assistant" if is_from_me else "user"
        messages.append({
            "role": role,
            "text": text,
            "timestamp": ts,
            "sender": sender_id,
            "service": service or "iMessage",
        })

    return messages


def import_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.json':
        with open(filepath, encoding='utf-8') as f:
            return json.load(f)
    elif ext == '.txt':
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
                        "service": "iMessage",
                    })
        return messages
    else:
        raise ValueError(f"Unsupported file format: {ext}. Use .json or .txt")
