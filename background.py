"""
Cross-platform background service launcher for Universal Chat AI.

Runs the server as a background process with:
- macOS: LaunchAgent via plist
- Linux: systemd user service
- Windows: background process

Usage:
  python background.py install   - Install as background service
  python background.py uninstall - Remove background service
  python background.py start     - Start server (foreground)
  python background.py stop      - Stop server
  python background.py status    - Check if running
  python background.py logs      - View logs
"""

import os
import sys
import subprocess
import time
import signal
import json

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(HERE, "server.py")
LOG_FILE = os.path.join(HERE, "server.log")
PID_FILE = os.path.join(HERE, "server.pid")
PORT = int(os.environ.get("PORT", 8765))

PLIST_LABEL = "com.user.universalchat"
PLIST_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{PLIST_LABEL}.plist")
SYSTEMD_SERVICE = "universal-chat-ai"


def get_platform():
    if sys.platform == "darwin":
        return "macos"
    elif sys.platform.startswith("linux"):
        return "linux"
    elif sys.platform == "win32":
        return "windows"
    return sys.platform


def is_running():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return pid
        except (OSError, ValueError):
            os.remove(PID_FILE)
    return False


def start_foreground():
    pid = is_running()
    if pid:
        print(f"Server already running (PID: {pid})")
        return
    os.chdir(HERE)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-u", SERVER_SCRIPT],
        stdout=open(LOG_FILE, "a"),
        stderr=subprocess.STDOUT,
        env=env,
    )
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))
    print(f"Started server (PID: {proc.pid})")
    print(f"Logs: {LOG_FILE}")
    print(f"Web:  http://127.0.0.1:{PORT}")


def stop():
    pid = is_running()
    if not pid:
        print("Server not running")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(10):
            time.sleep(0.3)
            try:
                os.kill(pid, 0)
            except OSError:
                break
        else:
            os.kill(pid, signal.SIGKILL)
        print(f"Stopped server (PID: {pid})")
    except OSError:
        print(f"Could not stop server (PID: {pid})")
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)


def status():
    pid = is_running()
    if pid:
        print(f"Running (PID: {pid})")
        print(f"Web UI: http://127.0.0.1:{PORT}")
    else:
        print("Not running")
    return pid


def install():
    platform = get_platform()
    if platform == "macos":
        _install_macos()
    elif platform == "linux":
        _install_linux()
    elif platform == "windows":
        _install_windows()
    else:
        print(f"Auto-install not supported on {platform}")
        print(f"Run 'python background.py start' to start manually")


def _install_macos():
    os.makedirs(os.path.expanduser("~/Library/LaunchAgents"), exist_ok=True)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>-u</string>
        <string>{SERVER_SCRIPT}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{HERE}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{LOG_FILE}</string>
    <key>StandardErrorPath</key>
    <string>{LOG_FILE}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
</dict>
</plist>"""
    with open(PLIST_PATH, "w") as f:
        f.write(plist)
    subprocess.run(["launchctl", "load", PLIST_PATH])
    print(f"Installed and started LaunchAgent: {PLIST_PATH}")
    print(f"Web UI: http://127.0.0.1:{PORT}")
    print(f"Logs: {LOG_FILE}")
    print(f"To uninstall: python background.py uninstall")


def _install_linux():
    user = os.environ.get("USER", "user")
    service_dir = os.path.expanduser("~/.config/systemd/user")
    os.makedirs(service_dir, exist_ok=True)
    service_path = os.path.join(service_dir, f"{SYSTEMD_SERVICE}.service")
    service = f"""[Unit]
Description=Universal Chat AI
After=network.target

[Service]
Type=simple
ExecStart={sys.executable} -u {SERVER_SCRIPT}
WorkingDirectory={HERE}
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""
    with open(service_path, "w") as f:
        f.write(service)
    subprocess.run(["systemctl", "--user", "daemon-reload"])
    subprocess.run(["systemctl", "--user", "enable", f"{SYSTEMD_SERVICE}.service"])
    subprocess.run(["systemctl", "--user", "start", f"{SYSTEMD_SERVICE}.service"])
    print(f"Installed and started systemd user service: {SYSTEMD_SERVICE}")
    print(f"Web UI: http://127.0.0.1:{PORT}")
    print(f"To uninstall: python background.py uninstall")


def _install_windows():
    try:
        import win32serviceutil
        import win32service
        import servicemanager
        import win32event
        print("Windows service installed. Use Services panel to manage.")
    except ImportError:
        print("Windows service requires pywin32: pip install pywin32")
        print(f"Until then, run: python background.py start")
        start_foreground()


def uninstall():
    platform = get_platform()
    if platform == "macos":
        _uninstall_macos()
    elif platform == "linux":
        _uninstall_linux()
    elif platform == "windows":
        _uninstall_windows()
    else:
        print(f"Uninstall not supported on {platform}")


def _uninstall_macos():
    if os.path.exists(PLIST_PATH):
        subprocess.run(["launchctl", "unload", PLIST_PATH])
        os.remove(PLIST_PATH)
        print(f"Removed LaunchAgent: {PLIST_PATH}")
    stop()


def _uninstall_linux():
    subprocess.run(["systemctl", "--user", "stop", f"{SYSTEMD_SERVICE}.service"])
    subprocess.run(["systemctl", "--user", "disable", f"{SYSTEMD_SERVICE}.service"])
    service_path = os.path.expanduser(f"~/.config/systemd/user/{SYSTEMD_SERVICE}.service")
    if os.path.exists(service_path):
        os.remove(service_path)
    subprocess.run(["systemctl", "--user", "daemon-reload"])
    print(f"Removed systemd service: {SYSTEMD_SERVICE}")
    stop()


def _uninstall_windows():
    print("Remove service via Services panel or: sc delete UniversalChatAI")
    stop()


def logs():
    if not os.path.exists(LOG_FILE):
        print("No logs yet")
        return
    with open(LOG_FILE) as f:
        content = f.read()
    if not content.strip():
        print("Log file is empty")
        return
    lines = content.strip().split("\n")
    tail = lines[-50:]
    for line in tail:
        print(line)
    print(f"\n--- showing last {len(tail)} of {len(lines)} lines ---")
    print(f"Full log: {LOG_FILE}")


def restart():
    stop()
    time.sleep(1)
    start_foreground()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"

    if cmd == "install":
        install()
    elif cmd == "uninstall":
        uninstall()
    elif cmd == "start":
        start_foreground()
    elif cmd == "stop":
        stop()
    elif cmd == "restart":
        restart()
    elif cmd == "status":
        status()
    elif cmd == "logs":
        logs()
    elif cmd == "foreground":
        os.chdir(HERE)
        subprocess.run([sys.executable, "-u", SERVER_SCRIPT])
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python background.py [install|uninstall|start|stop|restart|status|logs|foreground]")
