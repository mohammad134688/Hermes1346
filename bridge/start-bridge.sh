#!/data/data/com.termux/files/usr/bin/bash
# ──────────────────────────────────────────────────────────────────
# Hermes Chat Bridge - Start Script
# Run this in Termux to start the bridge server
# ──────────────────────────────────────────────────────────────────

set -e

# Config
PORT=${HERMES_CHAT_PORT:-8765}
PROOT_DISTRO=${HERMES_PROOT_DISTRO:-ubuntu}
PROOT_USER=${HERMES_PROOT_USER:-root}
LOG_FILE="/tmp/hermes_bridge.log"
PID_FILE="/tmp/hermes_bridge.pid"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo -e "${BLUE}  Hermes Chat Bridge Server${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"

# Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo -e "${YELLOW}⚠️  Bridge already running (PID: $OLD_PID)${NC}"
        echo -e "   Kill with: kill $OLD_PID"
        exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

# Check proot-distro
if ! command -v proot-distro &>/dev/null; then
    echo -e "${RED}❌ proot-distro not found. Install with:${NC}"
    echo "   pkg install proot-distro"
    exit 1
fi

# Check if distro exists
if ! proot-distro list 2>/dev/null | grep -q "$PROOT_DISTRO"; then
    echo -e "${RED}❌ Distro '$PROOT_DISTRO' not installed.${NC}"
    echo "   Install with: proot-distro install $PROOT_DISTRO"
    exit 1
fi

# Check hermes inside proot
echo -e "${BLUE}🔍 Checking Hermes inside PRoot...${NC}"
if proot-distro login "$PROOT_DISTRO" --user "$PROOT_USER" -- bash -c "which hermes" &>/dev/null; then
    echo -e "${GREEN}✅ Hermes found${NC}"
else
    echo -e "${YELLOW}⚠️  Hermes not found inside PRoot. Bridge will start but chat may fail.${NC}"
fi

# Find bridge script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BRIDGE_SCRIPT="$SCRIPT_DIR/hermes_bridge.py"

if [ ! -f "$BRIDGE_SCRIPT" ]; then
    echo -e "${RED}❌ hermes_bridge.py not found at: $BRIDGE_SCRIPT${NC}"
    exit 1
fi

# Start server
echo -e "${BLUE}🚀 Starting bridge server on port $PORT...${NC}"
nohup python3 "$BRIDGE_SCRIPT" \
    --port "$PORT" \
    --proot-distro "$PROOT_DISTRO" \
    --proot-user "$PROOT_USER" \
    > "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"
echo -e "${GREEN}✅ Bridge started (PID: $(cat $PID_FILE))${NC}"
echo ""
echo -e "📱 Android app should connect to: ${GREEN}http://127.0.0.1:$PORT${NC}"
echo -e "📋 Log file: $LOG_FILE"
echo -e "🛑 Stop with: kill \$(cat $PID_FILE)"
echo ""
