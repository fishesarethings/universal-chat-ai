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
    'Facebook Messenger': {
        'root_only': True,
        'db': '/data/data/com.facebook.orca/databases/',
        'backup_cmd': 'com.facebook.orca',
        'parser': 'generic',
    },
    'Snapchat': {
        'root_only': True,
        'db': '/data/data/com.snapchat.android/databases/',
        'backup_cmd': 'com.snapchat.android',
        'parser': 'generic',
    },
    'Instagram': {
        'root_only': True,
        'db': '/data/data/com.instagram.android/databases/',
        'backup_cmd': 'com.instagram.android',
        'parser': 'generic',
    },
    'WeChat': {
        'root_only': True,
        'db': '/data/data/com.tencent.mm/databases/',
        'backup_cmd': 'com.tencent.mm',
        'parser': 'generic',
    },
    'Viber': {
        'root_only': True,
        'db': '/data/data/com.viber.voip/databases/',
        'backup_cmd': 'com.viber.voip',
        'parser': 'generic',
    },
    'Telegram': {
        'root_only': True,
        'db': '/data/data/org.telegram.messenger/databases/',
        'backup_cmd': 'org.telegram.messenger',
        'parser': 'telegram',
    },
    'Line': {
        'root_only': True,
        'db': '/data/data/jp.naver.line.android/databases/',
        'backup_cmd': 'jp.naver.line.android',
        'parser': 'generic',
    },
    'Skype': {
        'root_only': True,
        'db': '/data/data/com.skype.raider/databases/',
        'backup_cmd': 'com.skype.raider',
        'parser': 'generic',
    },
    'GroupMe': {
        'root_only': True,
        'db': '/data/data/com.groupme.android/databases/',
        'backup_cmd': 'com.groupme.android',
        'parser': 'generic',
    },
    'Kik': {
        'root_only': True,
        'db': '/data/data/kik.android/databases/',
        'backup_cmd': 'kik.android',
        'parser': 'generic',
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


def extract(udid=None, selected_apps=None, max_messages=None, progress_cb=None):
    if not is_installed():
        install_cmd = "brew install android-platform-tools" if sys.platform == "darwin" else "apt install adb"
        raise RuntimeError(f"adb not found. Install: {install_cmd}")

    devices = detect_devices()
    if not devices:
        raise RuntimeError("No Android device found. Connect via USB and enable USB debugging.")

    if not udid:
        udid = devices[0]['udid']

    print(f"  Connected: {devices[0]['name']} (Android {devices[0].get('android', '?')})")
    if progress_cb: progress_cb(10, f"Connected: {devices[0]['name']}")

    root = has_root(udid)
    print(f"  Root access: {'Yes' if root else 'No'}")
    if progress_cb: progress_cb(15, f"Root: {'Yes' if root else 'No'}")

    if not selected_apps:
        selected_apps = [name for name, config in ANDROID_APPS.items()
                         if not config.get('root_only', False) or root]

    all_messages = []
    total_apps = len(selected_apps)

    for i, app_name in enumerate(selected_apps):
        config = ANDROID_APPS.get(app_name)
        if not config:
            continue

        if config.get('root_only') and not root:
            print(f"  Skipping {app_name} (needs root)")
            continue

        pct = 15 + int((i / max(total_apps, 1)) * 75)
        if progress_cb: progress_cb(pct, f"Extracting {app_name}...")
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

    if progress_cb: progress_cb(100, f"Done! {len(all_messages)} messages from {len(selected_apps)} apps")
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


def _try_parse_whatsapp(cur, messages):
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


def _try_parse_signal(cur, messages):
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


def _try_decrypt_and_parse(udid, remote_path, app, db_name, tmp_dir, messages):
    """Try to decrypt an encrypted SQLCipher database using key from device."""
    import shutil as _sh
    sqlcipher = _sh.which('sqlcipher')
    if not sqlcipher:
        print(f"    sqlcipher not installed. Try: brew install sqlcipher")
        return
    try:
        if app == 'whatsapp':
            key_file = '/data/data/com.whatsapp/files/aw_key'
        elif app == 'signal':
            key_file = '/data/data/org.thoughtcrime.securesms/files/backup_key'
        else:
            return
        cmd = ["adb"]
        if udid: cmd.extend(["-s", udid])
        key_result = subprocess.run(cmd + ["shell", "su", "-c", f"cat {key_file}"], capture_output=True, text=True, timeout=10)
        key = key_result.stdout.strip()
        if not key:
            print(f"    Could not read encryption key")
            return
        import tempfile
        local_db = os.path.join(tmp_dir, db_name)
        pull = ["adb"]
        if udid: pull.extend(["-s", udid])
        subprocess.run(pull + ["shell", "su", "-c", f"cat {remote_path}"], stdout=open(local_db,'wb'), stderr=subprocess.PIPE, timeout=30)
        if not os.path.exists(local_db) or os.path.getsize(local_db) == 0:
            return
        decrypted = os.path.join(tmp_dir, "decrypted.db")
        import subprocess as _sp
        _sp.run([sqlcipher, local_db, f'PRAGMA key="{key}"', f'ATTACH DATABASE "{decrypted}" AS plaintext KEY ""',
                 'SELECT sqlcipher_export("plaintext")', 'DETACH DATABASE plaintext',
                 '.quit'], capture_output=True, timeout=30)
        if os.path.exists(decrypted) and os.path.getsize(decrypted) > 0:
            dconn = sqlite3.connect(f"file:{decrypted}?mode=ro", uri=True)
            dcur = dconn.cursor()
            if app == 'whatsapp':
                _try_parse_whatsapp(dcur, messages)
            elif app == 'signal':
                _try_parse_signal(dcur, messages)
            dconn.close()
            os.remove(decrypted)
    except Exception as e:
        print(f"    Decryption failed: {e}")


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
                    _try_parse_whatsapp(cur, messages)
                except sqlite3.DatabaseError:
                    print(f"    WhatsApp DB encrypted, trying to decrypt...")
                    _try_decrypt_and_parse(udid, db_path, 'whatsapp', 'msgstore.db', tmp_dir, messages)
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
                except sqlite3.DatabaseError:
                    print(f"    Signal DB encrypted, trying to decrypt...")
                    _try_decrypt_and_parse(udid, db_path, 'signal', 'signal.db', tmp_dir, messages)
                except:
                    pass

            elif parser_type == 'generic':
                try:
                    messages = _generic_scan_db(cur, db_path)
                except:
                    pass

            conn.close()
    except Exception as e:
        print(f"    DB error: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return messages


def _generic_scan_db(cur, db_path):
    """Scan ANY SQLite database for message-like text."""
    messages = []
    try:
        try:
            tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        except sqlite3.DatabaseError:
            print(f"    Cannot read database (maybe encrypted): {os.path.basename(db_path)}")
            return []
        for table in tables:
            try:
                cols = [r[1] for r in cur.execute(f'PRAGMA table_info("{table}")').fetchall()]
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
                rows = cur.execute(f'SELECT {sel} FROM "{table}" ORDER BY {order} ASC').fetchall()
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
    except:
        pass
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
