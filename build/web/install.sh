#!/bin/bash
# Universal Chat AI - One-line install for macOS
# Run: bash <(curl -s https://fishesarethings.github.io/universal-chat-ai/install.sh)

set -e
echo ""
echo "  🧠  Universal Chat AI"
echo "  ─────────────────────"
echo "  📥  Downloading..."

cd /tmp
curl -sL "https://github.com/fishesarethings/universal-chat-ai/releases/latest/download/UniversalChatAI.app.zip" -o UniversalChatAI.app.zip
unzip -q -o UniversalChatAI.app.zip
rm UniversalChatAI.app.zip

# Move to Applications
if [ -d "/Applications/Universal Chat AI.app" ]; then
    rm -rf "/Applications/Universal Chat AI.app"
fi
mv "Universal Chat AI.app" /Applications/

echo "  ✅  Installed to /Applications"
echo "  🚀  Opening..."
open "/Applications/Universal Chat AI.app"
echo ""
echo "  First time? Right-click the app → Open"
echo ""
