#!/bin/bash
# Universal Chat AI - Installer
set -e
echo ""; echo "  🧠  Universal Chat AI"; echo "  ─────────────────────"
echo "  📥  Downloading..."
cd /tmp
URL="https://github.com/fishesarethings/universal-chat-ai/releases/latest/download/UniversalChatAI.app.zip"
if curl -sfL "$URL" -o UniversalChatAI.app.zip && [ -s UniversalChatAI.app.zip ]; then
  unzip -q -o UniversalChatAI.app.zip && rm UniversalChatAI.app.zip
  APP="/Applications/Universal Chat AI.app"
  if [ -d "$APP" ]; then rm -rf "$APP"; fi
  mv "Universal Chat AI.app" /Applications/
  # Remove quarantine flag so macOS doesn't block it
  xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true
  echo "  ✅  Installed to /Applications"
  echo "  🚀  Opening..."
  open "$APP"
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
