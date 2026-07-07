# HermesChat 🤖💬

Android chat client for [Hermes Agent](https://github.com/NousResearch/hermes-agent) — connect directly to your Hermes instance running in Termux + PRoot Ubuntu, without gateway.

## Architecture

```
┌──────────────────┐      HTTP       ┌─────────────────┐     subprocess     ┌──────────────────┐
│   Android App    │ ←─────────────→ │  Bridge Server  │ ←────────────────→ │  Hermes (PRoot)  │
│  (HermesChat)    │  127.0.0.1:8765 │  (Python/Async) │                    │  hermes chat -q  │
│  Material Design │                  │  Termux native  │                    │  Ubuntu terminal  │
└──────────────────┘                  └─────────────────┘                    └──────────────────┘
```

## Features

- 🌙 Dark theme with Material Design 3
- 🔄 Session persistence (conversation context preserved)
- 📡 Real-time connection status indicator
- ⚡ Fast response display with typing indicator
- 📱 Optimized for low-end devices (Samsung A03s tested)
- 🔧 Configurable server URL
- 📋 One-tap new chat / session reset

## Setup

### 1. Install Bridge Server (in Termux)

```bash
# Copy bridge files to Termux
cp -r bridge/ ~/hermes-chat/bridge/
chmod +x ~/hermes-chat/bridge/*.sh

# Start the bridge
~/hermes-chat/bridge/start-bridge.sh
```

### 2. Install Android App

1. Build the APK (see below) or download from Releases
2. Install on your device
3. Open HermesChat
4. The default server URL is `http://127.0.0.1:8765`
5. You should see the connection status turn green ✅

### 3. Auto-start on Boot (Optional)

```bash
# Copy boot script
cp ~/hermes-chat/bridge/start-on-boot.sh ~/.termux/boot/
chmod +x ~/.termux/boot/start-on-boot.sh
```

## Build APK

### Option A: GitHub Actions (Recommended)

1. Push this repo to GitHub
2. Go to Actions tab → Run workflow
3. Download the APK from artifacts

### Option B: Local Build

```bash
# On a machine with Android SDK
./gradlew assembleDebug

# APK will be at:
# app/build/outputs/apk/debug/app-debug.apk
```

## Bridge Server

The bridge server is a lightweight Python HTTP server that runs in Termux (not PRoot).

### API Endpoints

| Method | Path | Body | Description |
|--------|------|------|-------------|
| `POST` | `/chat` | `{"message": "...", "session_id": "..."}` | Send message |
| `POST` | `/new` | `{}` | Start new session |
| `GET` | `/status` | - | Check server status |
| `GET` | `/health` | - | Health check |

### Configuration

```bash
# Custom port
HERMES_CHAT_PORT=8765 python3 hermes_bridge.py

# Custom PRoot distro
python3 hermes_bridge.py --proot-distro ubuntu

# CLI options
python3 hermes_bridge.py --port 8765 --host 127.0.0.1 --proot-distro ubuntu
```

### Logs

```bash
# View logs
tail -f /tmp/hermes_bridge.log
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| App shows "disconnected" | Make sure bridge is running: `start-bridge.sh` |
| Slow responses | Normal on low-end devices. Hermes needs 5-15s to process. |
| "Connection refused" | Check bridge is running on correct port: `curl http://127.0.0.1:8765/health` |
| Hermes not found | Install hermes inside PRoot: `proot-distro login ubuntu -- bash -c "curl -fsSL https://hermes-agent.nousresearch.com/install.sh \| bash"` |
| Session not persisting | Check `/tmp/hermes_bridge.log` for errors |
| Bridge dies after Termux background | Use `start-on-boot.sh` with Termux:Boot |

## Project Structure

```
HermesChat/
├── .github/workflows/build.yml    # CI/CD
├── app/
│   ├── build.gradle.kts
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── java/com/hermes/chat/
│       │   ├── MainActivity.kt      # Chat UI
│       │   ├── ChatAdapter.kt       # Message list
│       │   ├── ChatMessage.kt       # Data model
│       │   ├── HermesClient.kt      # HTTP client
│       │   ├── SettingsManager.kt   # Preferences
│       │   └── SettingsActivity.kt  # Settings UI
│       └── res/                     # Layouts, drawables, etc.
├── bridge/
│   ├── hermes_bridge.py             # Bridge server
│   ├── start-bridge.sh              # Start script
│   ├── stop-bridge.sh               # Stop script
│   └── start-on-boot.sh            # Termux:Boot auto-start
├── build.gradle.kts
├── settings.gradle.kts
└── README.md
```

## Requirements

- **Android**: 10+ (API 29)
- **Termux**: Latest from F-Droid
- **PRoot**: `proot-distro install ubuntu`
- **Hermes Agent**: Installed inside Ubuntu
- **Python 3**: `pkg install python`

## License

MIT
