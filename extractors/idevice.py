"""
iOS/iPhone message extractor via USB using libimobiledevice.
Connect iPhone via USB, trust the computer, then extract messages.

Requires: brew install libimobiledevice
Or on Linux: apt install libimobiledevice6
"""

import os, sys, plistlib, shutil, sqlite3, subprocess, tempfile, pty, select, fcntl, re, time
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


def create_backup(udid, output_dir, apps=None, progress_cb=None, backup_password=None):
    if progress_cb: progress_cb(0, "Starting backup...")
    print(f"  Creating iPhone backup (this may take a few minutes)...")
    print(f"  Keep your iPhone unlocked and screen on.")

    # Check if phone is paired/trusted
    try:
        pair_check = subprocess.run(["idevicepair", "validate", "-u", udid], capture_output=True, text=True, timeout=10)
        if pair_check.returncode != 0:
            err = (pair_check.stderr or pair_check.stdout or "").strip()
            if progress_cb: progress_cb(0, f"❌ Phone not trusted: {err}")
            print(f"  ❌ Phone not trusted. Tap 'Trust' on your iPhone.\n  {err}")
            return None
    except Exception as e:
        print(f"  ⚠️ Pair check failed: {e}")

    if progress_cb: progress_cb(5, "Backing up messages...")

    cmd = ["idevicebackup2", "backup", output_dir]
    if udid: cmd.extend(["-u", udid])

    # Quick diagnostic: try a different temp dir to see if it instantly errors
    if progress_cb: progress_cb(5, "Diagnosing...")
    diag_dir = tempfile.mkdtemp(prefix="iphone_diag_")
    try:
        diag_cmd = ["idevicebackup2", "backup", diag_dir]
        if udid: diag_cmd.extend(["-u", udid])
        diag_env = os.environ.copy()
        if backup_password: diag_env["BACKUP_PASSWORD"] = backup_password
        quick_check = subprocess.run(diag_cmd, capture_output=True, text=True, timeout=10, input="", env=diag_env)
        if quick_check.returncode != 0:
            err = (quick_check.stderr or quick_check.stdout or "").strip()[:300]
            low = err.lower()
            if "password" in low and ("set" in low or "required" in low):
                msg = "❌ Encrypted backup — go to Settings → General → Transfer or Reset → Reset Encrypted Backup Password"
            elif "trust" in low:
                msg = "❌ Tap 'Trust' on your iPhone, then try again"
            elif "lock" in low or "passcode" in low:
                msg = "❌ Unlock your iPhone and keep screen on"
            else:
                msg = f"❌ {err}"
            if progress_cb: progress_cb(0, msg)
            print(f"  {msg}")
            return None
        print(f"  Quick check OK")
    except subprocess.TimeoutExpired:
        print(f"  Backup started — proceeding with live progress")
    except Exception as e:
        print(f"  ℹ️  Diagnostics: {e}")
    finally:
        shutil.rmtree(diag_dir, ignore_errors=True)

    if progress_cb: progress_cb(5, "Running backup...")

    # Set backup password env var in case device prompts
    env = os.environ.copy()
    if backup_password:
        env["BACKUP_PASSWORD"] = backup_password

    master_fd, slave_fd = pty.openpty()
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=slave_fd,
                                stderr=slave_fd, close_fds=True, env=env)
    except Exception as e:
        os.close(master_fd); os.close(slave_fd)
        if progress_cb: progress_cb(0, f"❌ Failed to start: {e}")
        return None
    os.close(slave_fd)

    fl = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

    buf = b''
    last_pct = 5
    start_time = time.time()
    last_output = start_time
    first_output_timeout = 20
    global_stuck_timeout = 120
    all_output = ""

    def parse_and_report(text):
        nonlocal last_pct
        m = re.search(r'(\d+\.?\d*)\s*%', text)
        if m:
            pct = int(float(m.group(1)))
            pct = max(5, min(95, pct))
            if pct > last_pct:
                last_pct = pct
                if progress_cb: progress_cb(pct, f"Backing up... {pct}%")
        low = text.lower()
        if "trust" in low and ("computer" in low or "this" in low):
            if progress_cb: progress_cb(last_pct, "❌ Tap 'Trust' on your iPhone"); return "error"
        if "password" in low and ("set" in low or "required" in low or "not" in low):
            if progress_cb: progress_cb(last_pct, "❌ Go to Settings → General → Transfer or Reset → Reset Encrypted Backup Password"); return "error"
        if ("lock" in low or "passcode" in low) and ("unlock" in low or "enter" in low or "screen" in low):
            if progress_cb: progress_cb(last_pct, "❌ Unlock your iPhone and keep screen on"); return "error"
        if "failed" in low or "error" in low:
            if progress_cb: progress_cb(last_pct, f"❌ {text.strip()[:200]}"); return "error"
        return "ok"

    while True:
        r, w, e = select.select([master_fd], [], [], 1.0)
        if r:
            try:
                data = os.read(master_fd, 4096)
                if not data: break
                last_output = time.time()
                buf += data
                all_output += data.decode('utf-8', errors='replace')
                decoded = buf.decode('utf-8', errors='replace')
                clean = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', decoded)
                clean = re.sub(r'\r', '\n', clean)
                for line in clean.split('\n'):
                    line = line.strip()
                    if line:
                        status = parse_and_report(line)
                        if status == "error":
                            proc.kill()
                            os.close(master_fd)
                            return None
            except OSError:
                break
        else:
            ret = proc.poll()
            if ret is not None:
                break
            elapsed = time.time() - start_time
            if elapsed > 300:
                proc.kill()
                if progress_cb: progress_cb(last_pct, "⏱️ Backup timed out (5 min)")
                os.close(master_fd)
                return None
            stuck_time = elapsed - (last_output - start_time)
            if elapsed > first_output_timeout and stuck_time > global_stuck_timeout:
                if progress_cb: progress_cb(last_pct, "⏱️ Backup stuck — unplug/replug iPhone and try again")
                proc.kill(); os.close(master_fd); return None

    proc.wait()
    # Read any remaining output after process exits
    try:
        while True:
            d = os.read(master_fd, 4096)
            if not d: break
            all_output += d.decode('utf-8', errors='replace')
    except: pass
    os.close(master_fd)

    return_code = proc.returncode
    manifest_path = os.path.join(output_dir, "Manifest.plist")
    if os.path.exists(manifest_path):
        if progress_cb: progress_cb(100, "Backup complete!")
        with open(manifest_path, 'rb') as f:
            manifest = plistlib.load(f)
        return manifest
    else:
        debug = all_output.strip()[:600]
        print(f"  ⚠️ idevicebackup2 exit code={return_code}, output: {debug}")
        if return_code != 0 and not debug:
            # Try direct capture to see the error
            try:
                diag = subprocess.run(["idevicebackup2", "backup", output_dir, "-u", udid],
                                      capture_output=True, text=True, timeout=15, input="")
                debug = (diag.stderr or diag.stdout or "").strip()[:300]
                print(f"  Direct capture: exit={diag.returncode}: {debug}")
            except Exception as e:
                debug = str(e)
        if progress_cb: progress_cb(last_pct, f"❌ Backup failed: {debug or 'unknown error (try manual: idevicebackup2 backup ...)'}")
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


def _is_encrypted(db_path):
    """Check if a SQLite database is encrypted."""
    try:
        with open(db_path, 'rb') as f:
            header = f.read(16)
        return not header.startswith(b'SQLite format 3')
    except:
        return True

def _generic_scan(db_path):
    """Scan ANY SQLite database for message-like data."""
    messages = []
    if _is_encrypted(db_path):
        print(f"    Skipping encrypted database: {os.path.basename(db_path)}")
        return messages
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        try:
            tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        except sqlite3.DatabaseError:
            print(f"    Cannot read database (maybe encrypted): {os.path.basename(db_path)}")
            conn.close()
            return []
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


def extract(udid=None, selected_apps=None, max_messages=None, progress_cb=None, backup_password=None):
    if not is_installed():
        install_cmd = "brew install libimobiledevice" if sys.platform == "darwin" else "apt install libimobiledevice6"
        raise RuntimeError(f"libimobiledevice not found. Install: {install_cmd}")

    devices = detect_devices()
    if not devices:
        raise RuntimeError("No iPhone found. Connect via USB and trust this computer.")

    if not udid:
        udid = devices[0]['udid']

    print(f"  Connected: {devices[0]['name']} (iOS {devices[0].get('ios', '?')})")
    if progress_cb: progress_cb(2, f"Connected: {devices[0]['name']}")

    if not selected_apps:
        selected_apps = list(EXTRACTABLE_FROM_BACKUP.keys())

    backup_dir = tempfile.mkdtemp(prefix="iphone_backup_")
    all_messages = []
    try:
        manifest = create_backup(udid, backup_dir, progress_cb=progress_cb, backup_password=backup_password)
        if manifest is None:
            raise RuntimeError("Backup failed — unlock phone, tap Trust, then try again")

        if progress_cb: progress_cb(95, "Reading messages...")
        for app_name in selected_apps:
            if app_name in EXTRACTABLE_FROM_BACKUP:
                print(f"  Extracting {app_name}...")
                msgs = extract_from_backup(backup_dir, app_name)
                all_messages.extend(msgs)
                print(f"    Got {len(msgs)} messages")

        all_messages.sort(key=lambda m: m.get('timestamp') or '')

        if max_messages and len(all_messages) > max_messages:
            all_messages = all_messages[-max_messages:]

        if progress_cb: progress_cb(100, f"Done! {len(all_messages)} messages found")
        return all_messages

    finally:
        shutil.rmtree(backup_dir, ignore_errors=True)
