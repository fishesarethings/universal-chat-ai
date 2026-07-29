# 🧠 Universal Chat AI

An AI trained on **your** messages. Runs entirely on your computer — nothing leaves your device.

## 🚀 How to Use

### Mac:
1. Go to https://fishesarethings.github.io/universal-chat-ai
2. Click "Download for Mac"
3. Open the downloaded file
4. Click "Start" in the Terminal window that opens
5. Your browser opens — start chatting!

**First time opening a downloaded app?**
Right-click the app → Open (instead of double-click)

### Windows / Linux:
```bash
pip install flask torch psutil pandas flask-cors
python server.py
```
Then open http://127.0.0.1:5050

### 📱 On your phone:
Once running on your computer, visit `http://YOUR_COMPUTER_IP:5050` from your phone.
Tap Share → Add to Home Screen (looks and works like a real app).

---

## What it does
- Reads your iMessages (Mac only, stays on your computer)
- Import chats from WhatsApp, Discord, Signal, Snapchat, Google Messages
- Trains an AI that talks like you
- Chat with it — it learns from your conversations
- All processing stays **on your computer**

## Importing chats
Export your data from any app, then drag the file into the Import tab:
- **WhatsApp**: Chat → Export Chat (without media)
- **Discord**: Settings → Privacy & Safety → Request Data
- **Google Messages**: https://takeout.google.com (select Messages)
- **Snapchat**: Settings → My Data → Request
- **Signal**: Signal Desktop → Preferences → Advanced → Export
- **iMessage**: Automatic on Mac!

## One-line install (Mac)
Open Terminal and paste:
```bash
bash <(curl -s https://fishesarethings.github.io/universal-chat-ai/install.sh)
```

## Build from source
```bash
git clone https://github.com/fishesarethings/universal-chat-ai.git
cd universal-chat-ai
pip install -r requirements.txt
python server.py
```

## Technical
- Custom GPT model with BPE tokenizer
- Built with Python, Flask, PyTorch
- Static PWA frontend hosted on GitHub Pages
- All data stays on-device
