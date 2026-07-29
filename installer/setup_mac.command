#!/bin/bash
# Universal Chat AI - macOS Setup
# Double-click this file to install and start

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo ""
echo "  🧠  Universal Chat AI — Setup"
echo "  ─────────────────────────────"
echo ""

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "  ❌ Python 3 not found. Installing via Homebrew..."
    if ! command -v brew &> /dev/null; then
        echo "  Installing Homebrew first..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    brew install python@3
fi

echo "  ✅  Python 3 found"

# Install dependencies
echo "  📦  Installing packages (one-time)..."
pip3 install flask torch psutil pandas flask-cors 2>&1 | tail -1

# Check if running by seeing if port 5050 is in use
if lsof -ti:5050 &>/dev/null; then
    echo ""
    echo "  ✅  Already running! Opening browser..."
    open http://127.0.0.1:5050
    exit 0
fi

# Start server
echo ""
echo "  🚀  Starting Universal Chat AI..."
echo "  📱  Open your browser or visit http://127.0.0.1:5050"
echo "  ⏹  Close this window to quit"
echo ""

cd "$DIR"
python3 server.py

echo ""
echo "  Server stopped."
read -p "  Press Enter to close..."
