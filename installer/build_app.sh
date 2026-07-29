#!/bin/bash
# Build "Universal Chat AI.app" for macOS
# Usage: bash build_app.sh

DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$DIR")"
APP_NAME="Universal Chat AI"
APP_PATH="$DIR/$APP_NAME.app"
DMG_PATH="$DIR/$APP_NAME.dmg"

echo "Building $APP_NAME.app..."

# Create .app structure
rm -rf "$APP_PATH"
mkdir -p "$APP_PATH/Contents/MacOS"
mkdir -p "$APP_PATH/Contents/Resources"

# Use osacompile to create the app launcher from AppleScript
osacompile -o "$APP_PATH" -e '
on run
    set appPath to POSIX path of (path to me)
    set repoPath to do shell script "dirname " & quoted form of appPath & "/../../.."
    set repoPath to do shell script "cd " & quoted form of repoPath & " && pwd"
    
    -- Check if already running
    try
        set isRunning to do shell script "lsof -ti:5050 2>/dev/null || echo ''"
        if isRunning is not "" then
            do shell script "open http://127.0.0.1:5050"
            display notification "Already running!" subtitle "Opening browser..." with title "Universal Chat AI"
            return
        end if
    end try
    
    -- Launch in terminal
    tell application "Terminal"
        activate
        do script "cd " & quoted form of repoPath & " && clear && echo \"\" && echo \"  🧠  Universal Chat AI\" && echo \"  ─────────────────────\" && echo \"\" && echo \"  ⏳  Checking setup...\" && echo \"\" && pip3 install flask torch psutil pandas flask-cors -q 2>/dev/null; python3 server.py; echo \"\"; echo \"  Server stopped.\"; read -p \"  Press Enter to close...\""
    end tell
    
    -- Wait for server, then open browser
    delay 2
    do shell script "open http://127.0.0.1:5050"
    display notification "Server started!" subtitle "Open your browser" with title "Universal Chat AI"
end
'

# Copy app icon (generate a simple one)
mkdir -p "$APP_PATH/Contents/Resources"

# Create a simple icon using sips (macOS built-in)
ICON_PATH="$APP_PATH/Contents/Resources/applet.icns"
if [ ! -f "$ICON_PATH" ]; then
    # Generate a simple colored square as icon
    echo "  Generating app icon..."
    python3 -c "
import struct, zlib, os
# Create a minimal 16x16 PNG with a green circle
width, height = 256, 256
def create_png():
    def make_row(y):
        row = b''
        for x in range(width):
            cx, cy = x - width//2, y - height//2
            dist = (cx*cx + cy*cy)**0.5
            r = min(width, height) // 2 - 8
            if dist < r:
                row += b'\\x00\\xd4\\xaa\\xff'
            else:
                row += b'\\x00\\x00\\x00\\x00'
        return row
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    raw = b''
    for y in range(height):
        raw += b'\\x00' + make_row(y)
    return b'\\x89PNG\\r\\n\\x1a\\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')

png_path = '/tmp/_app_icon.png'
with open(png_path, 'wb') as f:
    f.write(create_png())
os.system(f'sips -s format icns \"{png_path}\" --out \"$ICON_PATH\" 2>/dev/null; rm -f \"{png_path}\"')
"
fi

# Copy the entire repo into the app bundle for portability
echo "  Bundling application files..."
mkdir -p "$APP_PATH/Contents/Resources/app"
cp -R "$REPO_DIR/server.py" "$APP_PATH/Contents/Resources/app/"
cp -R "$REPO_DIR/model.py" "$APP_PATH/Contents/Resources/app/"
cp -R "$REPO_DIR/train.py" "$APP_PATH/Contents/Resources/app/"
cp -R "$REPO_DIR/requirements.txt" "$APP_PATH/Contents/Resources/app/"
cp -R "$REPO_DIR/extractors" "$APP_PATH/Contents/Resources/app/"
cp -R "$REPO_DIR/web" "$APP_PATH/Contents/Resources/app/"

# Update the script in the app to point to bundled resources
echo "  Done! $APP_PATH"
echo ""

# Optionally create DMG
if [ "$1" = "--dmg" ]; then
    echo "Creating DMG..."
    rm -f "$DMG_PATH"
    hdiutil create -volname "$APP_NAME" -srcfolder "$APP_PATH" -ov -format UDZO "$DMG_PATH" 2>/dev/null
    echo "  DMG: $DMG_PATH"
fi

echo ""
echo "  ✅  Built: $APP_PATH"
echo "  📦  Double-click '$APP_NAME.app' to run"
echo "  📤  Share the .app or zip it for others"
