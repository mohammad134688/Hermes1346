#!/data/data/com.termux/files/usr/bin/bash
# ──────────────────────────────────────────────────────────────────
# Hermes Chat Bridge - Stop Script
# ──────────────────────────────────────────────────────────────────

PID_FILE="/tmp/hermes_bridge.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        rm -f "$PID_FILE"
        echo "✅ Bridge stopped (PID: $PID)"
    else
        rm -f "$PID_FILE"
        echo "⚠️  Bridge was not running (stale PID file removed)"
    fi
else
    echo "⚠️  No PID file found. Bridge may not be running."
    # Try to kill by process name
    pkill -f "hermes_bridge.py" 2>/dev/null && echo "✅ Killed by process name" || true
fi
