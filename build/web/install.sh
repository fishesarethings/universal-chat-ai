#!/bin/bash
# Universal Chat AI - Installer
set -e
echo ""; echo "  🧠  Universal Chat AI"; echo "  ─────────────────────"
echo "  📥  Downloading..."
cd /tmp
# Try release asset first, fall back to source
URL="https://github.com/fishesarethings/universal-chat-ai/releases/latest/download/UniversalChatAI.app.zip"
if curl -sfL "$URL" -o UniversalChatAI.app.zip && [ -s UniversalChatAI.app.zip ]; then
  unzip -q -o UniversalChatAI.app.zip && rm UniversalChatAI.app.zip
  if [ -d "/Applications/Universal Chat AI.app" ]; then rm -rf "/Applications/Universal Chat AI.app"; fi
  mv "Universal Chat AI.app" /Applications/
  echo "  ✅  Installed to /Applications"
  open "/Applications/Universal Chat AI.app"
else
  # No release - run from source
  rm -f UniversalChatAI.app.zip 2>/dev/null
  if [ ! -d "$HOME/universal_chat_ai" ]; then
    echo "  Cloning source..."
    git clone --depth=1 https://github.com/fishesarethings/universal-chat-ai.git "$HOME/universal_chat_ai"
  fi
  echo "  🚀  Starting from source..."
  cd "$HOME/universal_chat_ai"
  pip3 install flask torch flask-cors -q 2>/dev/null
  python3 server.py &
  sleep 2; open http://127.0.0.1:5050
fi
