"""
Deploy script for Universal Chat AI.

Creates:
  - build/web/     -> Static PWA frontend (host anywhere: GitHub Pages, Netlify, Vercel)
  - build/backend/ -> Downloadable Python backend bundle

Usage:
  python deploy.py            Build both frontend and backend
  python deploy.py frontend   Build only static frontend
  python deploy.py backend    Build only downloadable backend
  python deploy.py host       Start a local HTTP server to test the frontend
"""

import os
import sys
import shutil
import zipfile
import subprocess
import json
import base64

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
WEB_SRC = os.path.join(HERE, "web")
BACKEND_FILES = [
    "server.py", "train.py", "model.py", "background.py",
    "requirements.txt", ".gitignore",
    "extractors/__init__.py", "extractors/imessage.py",
    "extractors/google_messages.py", "extractors/discord.py",
    "extractors/signal_.py", "extractors/whatsapp.py",
    "extractors/snapchat.py", "extractors/generic.py",
]


def clean_build():
    if os.path.exists(BUILD):
        shutil.rmtree(BUILD)


def build_frontend():
    out = os.path.join(BUILD, "web")
    os.makedirs(out, exist_ok=True)

    for fname in os.listdir(WEB_SRC):
        shutil.copy2(os.path.join(WEB_SRC, fname), os.path.join(out, fname))

    install_sh = os.path.join(HERE, "install.sh")
    if os.path.exists(install_sh):
        shutil.copy2(install_sh, os.path.join(out, "install.sh"))

    print(f"  Frontend: {out}/  ({len(os.listdir(out))} files)")


def build_backend():
    out = os.path.join(BUILD, "backend")
    os.makedirs(out, exist_ok=True)

    for src in BACKEND_FILES:
        src_path = os.path.join(HERE, src)
        dst_path = os.path.join(out, src)
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        shutil.copy2(src_path, dst_path)

    zip_path = os.path.join(BUILD, "desktop-backend.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(out):
            for f in files:
                file_path = os.path.join(root, f)
                arcname = os.path.relpath(file_path, out)
                z.write(file_path, arcname)

    shutil.rmtree(out)
    print(f"  Backend: {zip_path}")


def build_onefile_backend():
    content = '''#!/usr/bin/env python3
"""Universal Chat AI - Desktop Backend (Single File Bundle)

Extract and run:
  python universal_chat_ai_bundle.py

Or on Mac/Linux:
  chmod +x universal_chat_ai_bundle.py
  ./universal_chat_ai_bundle.py

Requires: pip install flask torch psutil pandas flask-cors
"""

import os
import sys
import json
import base64
import shutil
import tempfile
import subprocess
import zipfile

BUNDLE_DATA = {bundle_data}

def main():
    tmp = tempfile.mkdtemp(prefix="ucai_")
    try:
        data = base64.b64decode(BUNDLE_DATA)
        zip_path = os.path.join(tmp, "bundle.zip")
        with open(zip_path, "wb") as f:
            f.write(data)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmp)
        os.chdir(tmp)
        print("Starting Universal Chat AI backend...")
        print(f"Web UI: http://127.0.0.1:8765")
        print("Press Ctrl+C to stop\\n")
        subprocess.run([sys.executable, "-u", "server.py"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    main()
'''

    backend_dir = os.path.join(BUILD, "_bundle")
    os.makedirs(backend_dir, exist_ok=True)
    for src in BACKEND_FILES:
        src_path = os.path.join(HERE, src)
        dst_path = os.path.join(backend_dir, src)
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        shutil.copy2(src_path, dst_path)

    zip_buffer = os.path.join(BUILD, "_bundle.zip")
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(backend_dir):
            for f in files:
                file_path = os.path.join(root, f)
                arcname = os.path.relpath(file_path, backend_dir)
                z.write(file_path, arcname)

    with open(zip_buffer, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    shutil.rmtree(backend_dir)
    os.remove(zip_buffer)

    bundle_script = content.replace("{bundle_data}", repr(encoded))
    bundle_path = os.path.join(BUILD, "universal-chat-ai.py")
    with open(bundle_path, "w") as f:
        f.write(bundle_script)
    os.chmod(bundle_path, 0o755)

    size = os.path.getsize(bundle_path)
    print(f"  Single-file bundle: {bundle_path} ({size/1024:.0f} KB)")


def build_all():
    clean_build()
    os.makedirs(BUILD, exist_ok=True)
    print("Building Universal Chat AI\\n")
    build_frontend()
    build_backend()
    build_onefile_backend()
    print(f"\\nDone! Build output: {BUILD}/")
    print("  - web/         -> Host on GitHub Pages, Netlify, Vercel, etc.")
    print("  - desktop-backend.zip -> Downloadable Python backend")
    print("  - universal-chat-ai.py -> Single-file bundle (run anywhere)")


def host_frontend():
    frontend_dir = os.path.join(BUILD, "web")
    if not os.path.exists(frontend_dir):
        build_frontend()
        frontend_dir = os.path.join(BUILD, "web")
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
    print(f"Serving frontend at http://127.0.0.1:{port}")
    os.chdir(frontend_dir)
    subprocess.run([sys.executable, "-m", "http.server", str(port)])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "all":
        build_all()
    elif cmd == "frontend":
        build_frontend()
    elif cmd == "backend":
        build_backend()
        build_onefile_backend()
    elif cmd == "host":
        host_frontend()
    else:
        print(f"Unknown: {cmd}\\nUsage: python deploy.py [all|frontend|backend|host]")
