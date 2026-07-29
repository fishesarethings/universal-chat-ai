"""
iOS/iPhone message extractor via USB using libimobiledevice.
Connect iPhone via USB, trust the computer, then extract messages.

Requires: brew install libimobiledevice
Or on Linux: apt install libimobiledevice6
"""

import os
import sys
import plistlib
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timedelta

name = "iPhone (USB)"
description = "Extract messages from iPhone via USB cable"
platforms = ["macOS", "Linux"]

APP_BUNDLE_IDS = {
    'iMessage': 'com.apple.mobilesms',
    'WhatsApp': 'net.whatsapp.WhatsApp',
    'Signal': 'org.thoughtcrime.Signal',
    'Telegram': 'ph.telegra.Telegraph',
    'Snapchat': 'com.toyopagroup.picaboo',
    'Facebook Messenger': 'com.facebook.Messenger',
}

BUNDLE_HASHES = {
    'com.apple.mobilesms': '3d0d7e5fb2ce288813306e4d4636395e047a3d28',
}

EXTRACTABLE_FROM_BACKUP = {
    'iMessage': {'enabled': True, 'file': '3d0d7e5fb2ce288813306e4d4636395e047a3d28', 'parser': 'imessage'},
    'WhatsApp': {'enabled': True, 'file': 'ChatStorage.sqlite', 'parser': 'whatsapp'},
    'Signal': {'enabled': True, 'file': 'Signal.sqlite', 'parser': 'signal'},
    'Telegram': {'enabled': True, 'file': 'telegram.sqlite', 'parser': 'telegram'},
    'Facebook Messenger': {'enabled': True, 'file': 'com.facebook.Messenger', 'parser': 'generic'},
    'Snapchat': {'enabled': True, 'file': 'com.toyopagroup.picaboo', 'parser': 'generic'},
    'Instagram': {'enabled': True, 'file': 'com.burbn.instagram', 'parser': 'generic'},
    'WeChat': {'enabled': True, 'file': 'com.tencent.xin', 'parser': 'generic'},
    'Viber': {'enabled': True, 'file': 'com.viber', 'parser': 'generic'},
    'GroupMe': {'enabled': True, 'file': 'com.groupme', 'parser': 'generic'},
    'Kik': {'enabled': True, 'file': 'com.kik', 'parser': 'generic'},
    'Line': {'enabled': True, 'file': 'com.linecorp.Line', 'parser': 'generic'},
    'Skype': {'enabled': True, 'file': 'com.skype', 'parser': 'generic'},
}


def is_available():
    if sys.platform == "darwin":
        return shutil.which("idevice_id") is not None
    return False


def is_installed():
    return shutil.which("idevice_id") is not None


def detect_devices():
    if not is_installed():
        return []
    try:
        result = subprocess.run(["idevice_id", "--list"], capture_output=True, text=True, timeout=10)
        devices = [d.strip() for d in result.stdout.strip().split("\n") if d.strip()]
        device_info = []
        for udid in devices:
            info = get_device_info(udid)
            device_info.append({"udid": udid, "name": info.get("DeviceName", udid), "model": info.get("ProductType", ""), "ios": info.get("ProductVersion", "")})
        return device_info
    except:
        return []


def get_device_info(udid=None):
    try:
        cmd = ["ideviceinfo"]
        if udid:
            cmd.extend(["-u", udid])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        info = {}
        for line in result.stdout.strip().split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                info[k.strip()] = v.strip()
        return info
    except:
        return {}


def get_available_apps(udid):
    apps = []
    for app_name, config in EXTRACTABLE_FROM_BACKUP.items():
        if config['enabled']:
            apps.append({"name": app_name, "file": config['file'], "parser": config['parser']})
    return apps


def create_backup(udid, output_dir, apps=None):
    print(f"  Creating iPhone backup (this may take a few minutes)...")
    try:
        cmd = ["idevicebackup2", "backup", "--full", output_dir]
        if udid:
            cmd.extend(["-u", udid])
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        manifest_path = os.path.join(output_dir, "Manifest.plist")
        if os.path.exists(manifest_path):
            with open(manifest_path, 'rb') as f:
                manifest = plistlib.load(f)
            return manifest
        else:
            print(f"  Backup created but no manifest found")
            return None
    except subprocess.TimeoutExpired:
        print(f"  Backup timed out. Try manually: idevicebackup2 backup --full {output_dir}")
        return None
    except Exception as e:
        print(f"  Backup failed: {e}")
        return None


def extract_from_backup(backup_dir, app_name):
    config = EXTRACTABLE_FROM_BACKUP.get(app_name)
    if not config:
        return []

    db_file = config['file']
    parser = config['parser']

    print(f"  Looking for {app_name} data in backup...")

    if app_name == 'iMessage':
        hashed_path = os.path.join(backup_dir, BUNDLE_HASHES['com.apple.mobilesms'])
        db_path = None
        if os.path.isdir(hashed_path):
            for f in os.listdir(hashed_path):
                if f.endswith('.sqlitedb'):
                    db_path = os.path.join(hashed_path, f)
                    break
        elif os.path.exists(hashed_path):
            db_path = hashed_path

        if db_path and os.path.exists(db_path):
            return _parse_imessage_db(db_path)
        return []

    if app_name == 'WhatsApp':
        return _search_backup_for(backup_dir, db_file, _parse_whatsapp_db)

    if app_name == 'Signal':
        return _search_backup_for(backup_dir, db_file, _parse_signal_db)

    if app_name == 'Telegram':
        return _search_backup_for(backup_dir, db_file, _parse_telegram_db)

    if config['parser'] == 'generic':
        return _search_backup_for(backup_dir, db_file, _generic_scan)

    return []


def _search_backup_for(backup_dir, target_file, parser_fn):
    for root, dirs, files in os.walk(backup_dir):
        for f in files:
            if f == target_file or f.endswith('.sqlite') and target_file.lower() in f.lower():
                db_path = os.path.join(root, f)
                try:
                    return parser_fn(db_path)
                except Exception as e:
                    print(f"    Found but couldn't parse: {e}")
                    continue
    return []


def _parse_imessage_db(db_path):
    messages = []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT m.text, m.is_from_me, m.date, m.service, h.id as sender
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                WHERE m.text IS NOT NULL AND m.text != ''
                ORDER BY m.date ASC
            """)
        except:
            try:
                cur.execute("""
                    SELECT m.text, m.is_from_me, m.date, NULL as service, h.id as sender
                    FROM message m
                    LEFT JOIN handle h ON m.handle_id = h.ROWID
                    WHERE m.text IS NOT NULL AND m.text != ''
                    ORDER BY m.date ASC
                """)
            except:
                conn.close()
                return []

        for text, is_from_me, date, service, sender in cur.fetchall():
            try:
                text = text.decode('utf-8') if isinstance(text, bytes) else text
            except:
                continue
            if not text or not text.strip():
                continue
            dt = None
            if date and date > 0:
                try:
                    dt = (datetime(2001, 1, 1) + timedelta(seconds=date / 1_000_000_000)).isoformat()
                except:
                    pass
            role = "assistant" if is_from_me else "user"
            try:
                sender = sender.decode('utf-8') if isinstance(sender, bytes) else sender
            except:
                sender = None
            try:
                svc = service.decode('utf-8') if isinstance(service, bytes) else (service or "iMessage")
            except:
                svc = "iMessage"
            messages.append({
                "role": role, "text": text.strip(),
                "timestamp": dt, "sender": sender, "service": "iMessage",
            })
        conn.close()
    except Exception as e:
        print(f"    iMessage parse error: {e}")
    return messages


def _parse_whatsapp_db(db_path):
    messages = []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if 'ZWAMESSAGE' in tables:
            try:
                cur.execute("SELECT ZTEXT, ZISFROMME, ZMESSAGEDATE, ZSENDERNAME FROM ZWAMESSAGE WHERE ZTEXT IS NOT NULL ORDER BY ZMESSAGEDATE ASC")
                for text, is_from_me, date, sender in cur.fetchall():
                    if not text or not str(text).strip():
                        continue
                    ts = None
                    if date:
                        try:
                            ts = datetime.fromtimestamp(date).isoformat()
                        except:
                            pass
                    messages.append({
                        "role": "assistant" if is_from_me else "user",
                        "text": str(text).strip(),
                        "timestamp": ts,
                        "sender": str(sender) if sender else None,
                        "service": "WhatsApp",
                    })
            except:
                pass
        conn.close()
    except:
        pass
    return messages


def _parse_signal_db(db_path):
    messages = []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        try:
            cur.execute("SELECT body, type, sent_at, source FROM messages WHERE body IS NOT NULL AND body != '' ORDER BY sent_at ASC")
            for body, msg_type, sent_at, source in cur.fetchall():
                ts = None
                if sent_at and sent_at > 0:
                    try:
                        ts = datetime.fromtimestamp(sent_at / 1000).isoformat()
                    except:
                        pass
                messages.append({
                    "role": "assistant" if str(msg_type) in ('outgoing', '1') else "user",
                    "text": str(body).strip(),
                    "timestamp": ts,
                    "sender": str(source) if source else None,
                    "service": "Signal",
                })
        except:
            pass
        conn.close()
    except:
        pass
    return messages


def _parse_telegram_db(db_path):
    messages = []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT m.message, m.from_id, m.date, p.first_name || ' ' || p.last_name as sender
                FROM messages m
                LEFT JOIN peers p ON m.from_id = p.id
                WHERE m.message IS NOT NULL AND m.message != ''
                ORDER BY m.date ASC
            """)
            for text, from_id, date, sender in cur.fetchall():
                if not text or not str(text).strip():
                    continue
                ts = datetime.fromtimestamp(date).isoformat() if date else None
                messages.append({
                    "role": "user",
                    "text": str(text).strip(),
                    "timestamp": ts,
                    "sender": str(sender) if sender else str(from_id) if from_id else None,
                    "service": "Telegram",
                })
        except:
            pass
        conn.close()
    except:
        pass
    return messages


def _generic_scan(db_path):
    """Scan ANY SQLite database for message-like data."""
    messages = []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for table in tables:
            try:
                cols = [r[1] for r in cur.execute(f"PRAGMA table_info(\"{table}\")").fetchall()]
            except:
                continue
            text_cols = [c for c in cols if c.lower() in ('text','message','body','content','data','caption','comment')]
            if not text_cols:
                text_cols = [c for c in cols if any(t in c.lower() for t in ('text','message','body','content','caption'))]
            ts_cols = [c for c in cols if any(t in c.lower() for t in ('date','time','timestamp','sent','created'))]
            if not text_cols:
                continue
            try:
                sel = ','.join(text_cols + ts_cols[:1])
                order = ts_cols[0] if ts_cols else '1'
                query = f"SELECT {sel} FROM \"{table}\" ORDER BY {order} ASC"
                rows = cur.execute(query).fetchall()
                for row in rows:
                    text = str(row[0]) if row[0] is not None else ''
                    if not text.strip() or text == 'None':
                        continue
                    ts = None
                    if len(row) > 1 and row[1]:
                        try:
                            ts = datetime.fromtimestamp(float(str(row[1])) / 1000).isoformat()
                        except:
                            try:
                                ts = datetime.fromtimestamp(float(str(row[1]))).isoformat()
                            except:
                                pass
                    messages.append({
                        "role": "user", "text": text.strip(),
                        "timestamp": ts, "sender": None,
                        "service": os.path.basename(db_path).replace('.sqlite','').replace('.db',''),
                    })
            except:
                continue
        conn.close()
    except:
        pass
    return messages


def extract(udid=None, selected_apps=None, max_messages=None):
    if not is_installed():
        install_cmd = "brew install libimobiledevice" if sys.platform == "darwin" else "apt install libimobiledevice6"
        raise RuntimeError(f"libimobiledevice not found. Install: {install_cmd}")

    devices = detect_devices()
    if not devices:
        raise RuntimeError("No iPhone found. Connect via USB and trust this computer.")

    if not udid:
        udid = devices[0]['udid']

    print(f"  Connected: {devices[0]['name']} (iOS {devices[0].get('ios', '?')})")

    if not selected_apps:
        selected_apps = list(EXTRACTABLE_FROM_BACKUP.keys())

    backup_dir = tempfile.mkdtemp(prefix="iphone_backup_")
    all_messages = []
    try:
        manifest = create_backup(udid, backup_dir)
        if manifest is None:
            raise RuntimeError("Backup failed or timed out")

        for app_name in selected_apps:
            if app_name in EXTRACTABLE_FROM_BACKUP:
                print(f"  Extracting {app_name}...")
                msgs = extract_from_backup(backup_dir, app_name)
                all_messages.extend(msgs)
                print(f"    Got {len(msgs)} messages")

        all_messages.sort(key=lambda m: m.get('timestamp') or '')

        if max_messages and len(all_messages) > max_messages:
            all_messages = all_messages[-max_messages:]

        return all_messages

    finally:
        shutil.rmtree(backup_dir, ignore_errors=True)
