#!/bin/bash
# Universal Chat AI - one command: installs everything, starts, opens browser
DIR="$HOME/universal_chat_ai"

echo ""; echo "  🧠  Universal Chat AI"; echo "  ─────────────────────"

if ! command -v python3 &>/dev/null; then echo "  ❌ Install Python 3: https://python.org"; exit 1; fi

# Kill old server
lsof -ti:8765 2>/dev/null | xargs kill 2>/dev/null || true

# Download/update repo
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

# Install phone tools (no sudo on Mac — brew installs to user-owned dirs)
if [[ "$OSTYPE" == "darwin"* ]]; then
  if ! command -v idevice_id &>/dev/null && command -v brew &>/dev/null; then
    echo "  📲  Installing iPhone support (libimobiledevice)..."
    brew install libimobiledevice 2>/dev/null || true
  fi
  if ! command -v adb &>/dev/null && command -v brew &>/dev/null; then
    echo "  📲  Installing Android support (android-platform-tools)..."
    brew install android-platform-tools 2>/dev/null || true
  fi
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
  if command -v apt-get &>/dev/null; then
    if ! command -v idevice_id &>/dev/null; then
      echo "  📲  Installing iPhone support..."
      sudo apt-get install -y libimobiledevice6 libimobiledevice-utils 2>/dev/null || true
    fi
    if ! command -v adb &>/dev/null; then
      echo "  📲  Installing Android support..."
      sudo apt-get install -y adb 2>/dev/null || true
    fi
  fi
fi

# Install Python deps
echo "  📦  Installing flask..."
python3 -m pip install flask flask-cors -q 2>/dev/null || true
echo "  📦  Installing torch..."
python3 -c "import torch" 2>/dev/null || python3 -m pip install torch -q 2>/dev/null || echo "  ⚠️  torch skipped — chat needs 'pip install torch'"

clear 2>/dev/null || true
echo ""; echo "  🧠  Universal Chat AI"; echo "  ─────────────────────"
echo "  ✅  Starting..."
cd "$DIR"
python3 server.py &
sleep 2
open http://127.0.0.1:8765 2>/dev/null || xdg-open http://127.0.0.1:8765 2>/dev/null || echo "  Open http://127.0.0.1:8765"
echo ""
echo "  📱  Plug in phone via USB (tap Trust on iPhone, USB Debugging on Android)"
echo "  💬  Open http://127.0.0.1:8765 → Train tab → Extract → Train → Chat"
echo "  ⏹   Quit: Ctrl+C in this Terminal"
echo ""; wait
