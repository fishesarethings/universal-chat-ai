#!/bin/bash
# One-line installer for Universal Chat AI
# Run in terminal: bash <(curl -s https://fishesarethings.github.io/universal-chat-ai/install.sh)

set -e

echo ""
echo "  🧠  Universal Chat AI"
echo "  ─────────────────────"
echo ""

# Detect OS
OS="$(uname -s)"
case "$OS" in
    Darwin)   OS="macos" ;;
    Linux)    OS="linux" ;;
    *)        echo "  ❌ Unsupported OS: $OS"; exit 1 ;;
esac

echo "  📥  Downloading for $OS..."

# Download repo
TMP_DIR=$(mktemp -d)
cd "$TMP_DIR"
curl -sL "https://github.com/fishesarethings/universal-chat-ai/archive/refs/heads/master.zip" -o repo.zip
unzip -q repo.zip
cd universal-chat-ai-master

# Install Python deps
echo "  📦  Installing packages..."
pip3 install flask torch psutil pandas flask-cors -q 2>/dev/null || pip install flask torch psutil pandas flask-cors -q 2>/dev/null

# Start
echo ""
echo "  🚀  Starting..."
echo "  📱  Open: http://127.0.0.1:5050"
echo "  ⏹  Close this window to quit"
echo ""

python3 server.py
