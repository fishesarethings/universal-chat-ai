"""
Android message extractor via USB using adb.
Connect Android via USB, enable USB debugging, then extract messages.

Requires: adb (brew install android-platform-tools)
"""

import os
import sys
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import re
from datetime import datetime

name = "Android (USB)"
description = "Extract messages from Android phone via USB cable"
platforms = ["macOS", "Linux", "Windows"]

# Android apps and their backup/DB locations
ANDROID_APPS = {
    'SMS/MMS': {
        'root_only': False,
        'uri': 'content://sms/',
        'columns': ['body', 'type', 'date', 'address'],
        'parser': 'sms',
    },
    'Google Messages': {
        'root_only': False,
        'uri': 'content://sms/',
        'columns': ['body', 'type', 'date', 'address'],
        'parser': 'sms',
    },
    'WhatsApp': {
        'root_only': True,
        'db': '/data/data/com.whatsapp/databases/msgstore.db',
        'backup_cmd': 'com.whatsapp',
        'parser': 'whatsapp',
    },
    'Signal': {
        'root_only': True,
        'db': '/data/data/org.thoughtcrime.securesms/databases/',
        'backup_cmd': 'org.thoughtcrime.securesms',
        'parser': 'signal',
    },
    'Telegram': {
        'root_only': True,
        'db': '/data/data/org.telegram.messenger/databases/',
        'backup_cmd': 'org.telegram.messenger',
        'parser': 'telegram',
    },
    'Discord': {
        'root_only': True,
        'db': '/data/data/com.discord/databases/',
        'backup_cmd': 'com.discord',
        'parser': 'discord',
    },
}


def is_available():
    return shutil.which("adb") is not None


def is_installed():
    return shutil.which("adb") is not None


def detect_devices():
    if not is_installed():
        return []
    try:
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
        lines = result.stdout.strip().split("\n")
        devices = []
        for line in lines[1:]:
            line = line.strip()
            if line and "device" in line and "offline" not in line:
                udid = line.split("\t")[0]
                info = get_device_info(udid)
                devices.append({
                    "udid": udid,
                    "name": info.get("ro.product.model", udid),
                    "model": info.get("ro.product.name", ""),
                    "android": info.get("ro.build.version.release", ""),
                })
        return devices
    except:
        return []


def get_device_info(udid=None):
    try:
        cmd = ["adb"]
        if udid:
            cmd.extend(["-s", udid])
        cmd.extend(["shell", "getprop"])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        info = {}
        for line in result.stdout.strip().split("\n"):
            m = re.match(r'\[([^\]]+)\]:\s*\[([^\]]*)\]', line)
            if m:
                info[m.group(1)] = m.group(2)
        return info
    except:
        return {}


def has_root(udid=None):
    cmd = ["adb"]
    if udid:
        cmd.extend(["-s", udid])
    cmd.extend(["shell", "su", "-c", "echo 1"])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return result.stdout.strip() == "1"
    except:
        return False


def get_available_apps(udid):
    root = has_root(udid)
    apps = []
    for name, config in ANDROID_APPS.items():
        available = not config.get('root_only', False) or root
        apps.append({
            "name": name,
            "available": available,
            "needs_root": config.get('root_only', False),
            "parser": config.get('parser', ''),
        })
    return apps


def extract(udid=None, selected_apps=None, max_messages=None):
    if not is_installed():
        install_cmd = "brew install android-platform-tools" if sys.platform == "darwin" else "apt install adb"
        raise RuntimeError(f"adb not found. Install: {install_cmd}")

    devices = detect_devices()
    if not devices:
        raise RuntimeError("No Android device found. Connect via USB and enable USB debugging.")

    if not udid:
        udid = devices[0]['udid']

    print(f"  Connected: {devices[0]['name']} (Android {devices[0].get('android', '?')})")

    root = has_root(udid)
    print(f"  Root access: {'Yes' if root else 'No'}")

    if not selected_apps:
        selected_apps = [name for name, config in ANDROID_APPS.items()
                         if not config.get('root_only', False) or root]

    all_messages = []

    for app_name in selected_apps:
        config = ANDROID_APPS.get(app_name)
        if not config:
            continue

        if config.get('root_only') and not root:
            print(f"  Skipping {app_name} (needs root)")
            continue

        print(f"  Extracting {app_name}...")
        parser = config.get('parser', '')

        if parser == 'sms':
            msgs = _extract_sms(udid, config)
        elif config.get('db'):
            msgs = _extract_db(udid, config, parser)
        elif config.get('backup_cmd'):
            msgs = _extract_via_backup(udid, config, parser)
        else:
            msgs = []

        all_messages.extend(msgs)
        print(f"    Got {len(msgs)} messages")

    all_messages.sort(key=lambda m: m.get('timestamp') or '')

    if max_messages and len(all_messages) > max_messages:
        all_messages = all_messages[-max_messages:]

    return all_messages


def _extract_sms(udid, config):
    messages = []
    try:
        cmd = ["adb"]
        if udid:
            cmd.extend(["-s", udid])
        columns = ','.join(config.get('columns', ['body', 'type', 'date', 'address']))
        cmd.extend(["shell", "content", "query", "--uri", config['uri'], "--projection", columns])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

        rows = result.stdout.strip().split("\n")
        for row in rows:
            if not row.strip() or row.startswith("Row"):
                continue
            fields = {}
            for part in re.findall(r'(\w+)=([^,]+)', row):
                k, v = part
                fields[k.strip()] = v.strip()

            body = fields.get('body', '')
            if not body or body == 'null':
                continue

            msg_type = fields.get('type', '1')
            role = "assistant" if msg_type == '2' else "user"
            ts = None
            date_str = fields.get('date', '')
            if date_str and date_str != 'null':
                try:
                    ts = datetime.fromtimestamp(int(date_str) / 1000).isoformat()
                except:
                    pass
            sender = fields.get('address', '')
            if sender == 'null':
                sender = None

            messages.append({
                "role": role,
                "text": body,
                "timestamp": ts,
                "sender": sender,
                "service": "Android SMS",
            })
    except Exception as e:
        print(f"    SMS error: {e}")

    return messages


def _extract_db(udid, config, parser_type):
    messages = []
    db_path = config.get('db', '')
    if not db_path:
        return messages

    tmp_dir = tempfile.mkdtemp(prefix="android_db_")
    local_path = os.path.join(tmp_dir, "data.db")

    try:
        pull_cmd = ["adb"]
        if udid:
            pull_cmd.extend(["-s", udid])
        pull_cmd.extend(["shell", "su", "-c", f"cat {db_path}"])
        with open(local_path, 'wb') as f:
            subprocess.run(pull_cmd, stdout=f, stderr=subprocess.PIPE, timeout=30)

        if os.path.getsize(local_path) > 0:
            import sqlite3
            conn = sqlite3.connect(f"file:{local_path}?mode=ro", uri=True)
            cur = conn.cursor()

            if parser_type == 'whatsapp':
                try:
                    cur.execute("SELECT data, key_from_me, timestamp, key_remote_jid FROM messages WHERE data IS NOT NULL ORDER BY timestamp ASC")
                    for text, is_from_me, ts, sender in cur.fetchall():
                        try:
                            text = text.decode('utf-8') if isinstance(text, bytes) else str(text)
                        except:
                            continue
                        if not text.strip():
                            continue
                        dt = datetime.fromtimestamp(ts / 1000).isoformat() if ts else None
                        messages.append({
                            "role": "assistant" if is_from_me else "user",
                            "text": text.strip(),
                            "timestamp": dt,
                            "sender": str(sender) if sender else None,
                            "service": "WhatsApp",
                        })
                except:
                    pass

            elif parser_type == 'signal':
                try:
                    cur.execute("SELECT body, type, sent_at, source FROM messages WHERE body IS NOT NULL AND body != '' ORDER BY sent_at ASC")
                    for body, msg_type, sent_at, source in cur.fetchall():
                        ts = datetime.fromtimestamp(sent_at / 1000).isoformat() if sent_at else None
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
    except Exception as e:
        print(f"    DB error: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return messages


def _extract_via_backup(udid, config, parser_type):
    messages = []
    backup_cmd = config.get('backup_cmd', '')
    if not backup_cmd:
        return messages

    tmp_dir = tempfile.mkdtemp(prefix="android_backup_")
    backup_file = os.path.join(tmp_dir, "backup.ab")

    try:
        cmd = ["adb"]
        if udid:
            cmd.extend(["-s", udid])
        cmd.extend(["backup", "-f", backup_file, "-noapk", backup_cmd])
        print(f"    Creating backup (accept on phone)...")
        subprocess.run(cmd, timeout=60)

        if os.path.exists(backup_file) and os.path.getsize(backup_file) > 0:
            print(f"    Backup created ({os.path.getsize(backup_file)} bytes)")
            print(f"    To fully extract, use: android-backup-extractor")
            print(f"    For now, try root-based extraction instead.")
    except subprocess.TimeoutExpired:
        print(f"    Backup timed out. Accept backup on your phone.")
    except Exception as e:
        print(f"    Backup error: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return messages


def import_file(filepath):
    """Import an Android SMS backup XML file."""
    messages = []
    try:
        if filepath.endswith('.xml'):
            tree = ET.parse(filepath)
            root = tree.getroot()
            for sms in root.findall('sms'):
                body = sms.get('body', '')
                if not body.strip():
                    continue
                type_ = sms.get('type', '1')
                role = "assistant" if type_ == '2' else "user"
                ts = sms.get('readable_date', sms.get('date', None))
                messages.append({
                    "role": role,
                    "text": body.strip(),
                    "timestamp": ts,
                    "sender": sms.get('address', None),
                    "service": "Android SMS",
                })
        return messages
    except Exception as e:
        raise RuntimeError(f"Failed to parse Android backup: {e}")
