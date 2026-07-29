#!/bin/bash
# Universal Chat AI - One-line install
# Run: bash <(curl -s https://fishesarethings.github.io/universal-chat-ai/install.sh)

set -e

echo ""
echo "  🧠  Universal Chat AI"
echo "  ─────────────────────"
echo ""

if [ "$(uname -s)" != "Darwin" ]; then
    echo "  ⚠️  This installer is for macOS."
    echo "  For other platforms, see: https://github.com/fishesarethings/universal-chat-ai"
    exit 1
fi

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "  ⏳  Installing Python..."
    if ! command -v brew &>/dev/null; then
        echo "  Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    brew install python@3
fi

# Download
echo "  📥  Downloading..."
TMP=$(mktemp -d)
cd "$TMP"
curl -sL "https://github.com/fishesarethings/universal-chat-ai/archive/refs/heads/master.zip" -o repo.zip
unzip -q repo.zip
cd universal-chat-ai-master

# Install deps
echo "  📦  Installing packages (one-time)..."
pip3 install flask torch psutil pandas flask-cors -q 2>/dev/null || true

# Move to Applications
APP_DIR="$HOME/Applications/Universal Chat AI"
mkdir -p "$APP_DIR"
cp -R "$TMP/universal-chat-ai-master/" "$APP_DIR/"
rm -rf "$TMP"

# Create launcher
LAUNCHER="$HOME/Desktop/Start Universal Chat AI.command"
cat > "$LAUNCHER" << 'EOF'
#!/bin/bash
cd "$HOME/Applications/Universal Chat AI"
pip3 install flask torch psutil pandas flask-cors -q 2>/dev/null || true
python3 server.py
EOF
chmod +x "$LAUNCHER"

echo ""
echo "  ✅  Installed!"
echo "  📁  Location: $APP_DIR"
echo "  🚀  Double-click: 'Start Universal Chat AI' on your Desktop"
echo ""
