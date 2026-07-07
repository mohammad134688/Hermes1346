#!/data/data/com.termux/files/usr/bin/bash
# ──────────────────────────────────────────────────────────────────
# Termux:Boot - Auto-start Hermes Chat Bridge
# Place in: ~/.termux/boot/start-hermes-chat.sh
# Make executable: chmod +x ~/.termux/boot/start-hermes-chat.sh
# ──────────────────────────────────────────────────────────────────

# Wait for system to stabilize
sleep 10

# Start bridge server
PORT=${HERMES_CHAT_PORT:-8765}
PROOT_DISTRO=${HERMES_PROOT_DISTRO:-ubuntu}
PROOT_USER=${HERMES_PROOT_USER:-root}

BRIDGE_DIR="$(dirname "$0")/../../hermes-chat/bridge"

# Fallback paths
for dir in \
    "$BRIDGE_DIR" \
    "$HOME/hermes-chat/bridge" \
    "$HOME/HermesChat/bridge" \
    "/sdcard/Download/hermes-chat/bridge"; do
    if [ -f "$dir/hermes_bridge.py" ]; then
        BRIDGE_DIR="$dir"
        break
    fi
done

if [ -f "$BRIDGE_DIR/hermes_bridge.py" ]; then
    nohup python3 "$BRIDGE_DIR/hermes_bridge.py" \
        --port "$PORT" \
        --proot-distro "$PROOT_DISTRO" \
        --proot-user "$PROOT_USER" \
        > /tmp/hermes_bridge.log 2>&1 &
    echo $! > /tmp/hermes_bridge.pid
fi
