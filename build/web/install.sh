#!/bin/bash
# Universal Chat AI - One command install & run
set -e
DIR="$HOME/universal_chat_ai"
echo ""; echo "  🧠  Universal Chat AI"; echo "  ─────────────────────"

if ! command -v python3 &>/dev/null; then echo "  ❌ Install Python 3: https://python.org"; exit 1; fi

if [ ! -d "$DIR" ]; then
  echo "  📥  Downloading..."
  if command -v git &>/dev/null; then
    git clone --depth=1 https://github.com/fishesarethings/universal-chat-ai.git "$DIR"
  else
    cd /tmp && curl -sL "https://github.com/fishesarethings/universal-chat-ai/archive/refs/heads/master.zip" -o repo.zip
    unzip -q repo.zip && rm repo.zip && mv universal-chat-ai-master "$DIR"
  fi
else
  echo "  📥  Updating..."
  cd "$DIR" && git pull --ff-only 2>/dev/null || true
fi

echo "  📦  Installing (may take a minute)..."
pip3 install flask torch flask-cors -q 2>/dev/null || true

clear 2>/dev/null || true
echo ""; echo "  🧠  Universal Chat AI"; echo "  ─────────────────────"
echo "  ✅  Starting server..."
cd "$DIR" && python3 server.py &
sleep 2
open http://127.0.0.1:5050 2>/dev/null || xdg-open http://127.0.0.1:5050 2>/dev/null || true
echo ""
echo "  Open http://127.0.0.1:5050 in your browser"
echo "  Plug in phone → Train tab → Extract → Chat!"
echo ""; wait
