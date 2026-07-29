#!/bin/bash
# Universal Chat AI - One command: downloads, installs, launches
set -e
DIR="$HOME/universal_chat_ai"
echo ""; echo "  🧠  Universal Chat AI"; echo "  ─────────────────────"

if ! command -v python3 &>/dev/null; then echo "  ❌ Install Python 3: https://python.org"; exit 1; fi

# Kill any old server
lsof -ti:8765 2>/dev/null | xargs kill 2>/dev/null || true

# Download
if [ ! -d "$DIR" ]; then
  echo "  📥  Downloading..."
  if command -v git &>/dev/null; then
    git clone --depth=1 https://github.com/fishesarethings/universal-chat-ai.git "$DIR"
  else
    curl -sL "https://github.com/fishesarethings/universal-chat-ai/archive/refs/heads/master.zip" -o /tmp/repo.zip
    unzip -q /tmp/repo.zip -d /tmp && rm /tmp/repo.zip
    mv /tmp/universal-chat-ai-master "$DIR"
  fi
elif command -v git &>/dev/null; then
  cd "$DIR" && git pull --ff-only 2>/dev/null || true
fi

# Install deps
echo "  📦  Installing (1/2) flask..."
python3 -m pip install flask flask-cors -q 2>/dev/null || true
echo "  📦  Installing (2/2) torch..."
python3 -c "import torch" 2>/dev/null || python3 -m pip install torch -q 2>/dev/null || echo "  ⚠️  torch skipped — AI needs 'pip install torch'"

clear 2>/dev/null || true
echo ""; echo "  🧠  Universal Chat AI"; echo "  ─────────────────────"
echo "  ✅  Starting..."
cd "$DIR"
python3 server.py &
sleep 2
open http://127.0.0.1:8765 2>/dev/null || xdg-open http://127.0.0.1:8765 2>/dev/null || echo "  Open http://127.0.0.1:8765"
echo ""
echo "  📱  Connect iPhone (USB): brew install libimobiledevice && plug in + tap Trust"
echo "  📱  Connect Android (USB): Settings → Developer Options → USB Debugging"
echo "  💬  Open http://127.0.0.1:8765 → Train tab → Extract → Train → Chat"
echo "  ⏹   Quit: Ctrl+C in this Terminal window"
echo ""; wait
