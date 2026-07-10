#!/bin/bash
# Start Hermes API Server
# Usage: bash start.sh [--port 8080]

PORT=${1:-8080}
cd "$(dirname "$0")"

echo "🚀 Starting Hermes API Server on port $PORT..."
echo "   URL:  http://127.0.0.1:$PORT/v1"
echo "   Key:  hermes-local-key"
echo "   Model: hermes"
echo ""
echo "   ChatBox Settings:"
echo "   ┌─────────────────────────────────────┐"
echo "   │ API URL: http://127.0.0.1:$PORT/v1  │"
echo "   │ API Key: hermes-local-key           │"
echo "   │ Model:   hermes                     │"
echo "   └─────────────────────────────────────┘"
echo ""
echo "   Press Ctrl+C to stop"
echo ""

python3 hermes_api_server.py --port "$PORT"
