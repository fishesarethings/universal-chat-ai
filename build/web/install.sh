#!/bin/bash
# Universal Chat AI - One command: downloads, installs, launches
set -e
DIR="$HOME/universal_chat_ai"
echo ""; echo "  🧠  Universal Chat AI"; echo "  ─────────────────────"

if ! command -v python3 &>/dev/null; then echo "  ❌ Install Python 3: https://python.org"; exit 1; fi

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

# Install deps (ignore torch errors — it's big, may already be installed)
echo "  📦  Installing dependencies..."
python3 -m pip install flask flask-cors -q 2>/dev/null || true
python3 -c "import torch" 2>/dev/null || python3 -m pip install torch -q 2>/dev/null || echo "  ⚠️  torch install skipped (AI will still work after manual install)"

clear 2>/dev/null || true
echo ""; echo "  🧠  Universal Chat AI"; echo "  ─────────────────────"
echo "  ✅  Starting..."
cd "$DIR"
python3 server.py &
sleep 2
open http://127.0.0.1:5050 2>/dev/null || xdg-open http://127.0.0.1:5050 2>/dev/null || echo "  Open http://127.0.0.1:5050"
echo ""
echo "  Connect your iPhone/Android via USB"
echo "  → Go to Train tab → Extract All Messages"
echo "  → Train → Chat!"
echo ""; wait
