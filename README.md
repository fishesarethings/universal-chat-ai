# Universal Chat AI

Train a personal AI on your messages from ANY messaging service and chat with it.

Works on **Mac, Linux, Windows**. Access from **iPhone, Android, or any browser**.

## Quick Start

```bash
pip install flask torch psutil pandas
python server.py
```

Open `http://127.0.0.1:5050` in your browser.
On your phone, visit `http://YOUR_COMPUTER_IP:5050` — tap Share → Add to Home Screen.

## Supported Services

| Service | How to Extract |
|---------|---------------|
| **iMessage** | Auto-detected on macOS (`~/Library/Messages/chat.db`) |
| **Google Messages** | Upload Google Takeout JSON or SMS Backup & Restore XML |
| **Discord** | Upload Discord Data Package (Request from Discord privacy settings) |
| **Signal** | Auto-detected from Signal Desktop (Mac/Linux) or upload JSON export |
| **WhatsApp** | Upload chat export .txt (Chat → Export Chat) |
| **Snapchat** | Upload Snapchat My Data .zip (from snapchat.com settings) |
| **Any service** | Upload JSON, CSV, TXT with auto-detection |

## Features

- **Chat interface** — Talk to your trained AI, PWA installable on phone
- **Real-time progress** — See training loss, epoch, ETA update live
- **Background service** — Run as LaunchAgent (Mac), systemd (Linux), or background process
- **Multi-source** — Combine messages from all your services into one model
- **Import/Export** — Upload files from any platform, export your data anytime

## Background Mode

```bash
# Install as background service (auto-starts on login)
python background.py install

# Start/Stop manually
python background.py start
python background.py stop

# View status or logs
python background.py status
python background.py logs

# Remove background service
python background.py uninstall

# Run in foreground (for testing)
python server.py
```

## Model Sizes

| Size | Parameters | Speed | Quality |
|------|-----------|-------|---------|
| Tiny | ~1M | Fastest | Basic |
| Small | ~4M | Fast | Good |
| Medium | ~12M | Moderate | Better |
| Large | ~25M | Slow | Best |

## Getting Your Data

### iMessage (macOS)
Automatic extraction — just click "Extract" in the app.

### Google Messages (Android)
1. Go to https://takeout.google.com
2. Deselect all, then select only "Messages"
3. Download the export and upload the JSON file
4. Or use SMS Backup & Restore app → export XML and upload

### Discord
1. Go to User Settings → Privacy & Safety
2. Click "Request Data" under "Request all of my data"
3. Download the package when ready, upload the ZIP

### Signal
- **Desktop**: If Signal Desktop is installed and synced, extraction is automatic
- **Android**: Use Signal backup feature, convert to JSON

### WhatsApp
1. Open a chat → More options → Export chat
2. Choose "Without media"
3. Upload the generated .txt file

### Snapchat
1. Go to Snapchat settings → My Data
2. Submit request, download ZIP
3. Upload the ZIP file
