#!/usr/bin/env python3
"""
Hermes API Server — OpenAI-compatible API that routes to Hermes Agent.

ChatBox / any OpenAI-compatible app → this server → hermes -z → full Hermes

Usage:
    python3 hermes_api_server.py [--port 8080] [--host 0.0.0.0]

Then in your chat app, set:
    API URL:  http://127.0.0.1:8080/v1
    API Key:  hermes-local-key (any string works)
    Model:    hermes
"""

import argparse
import json
import subprocess
import sys
import time
import uuid
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# ── Config ──────────────────────────────────────────────────────────────
DEFAULT_PORT = 8080
DEFAULT_HOST = "0.0.0.0"
API_KEY = "hermes-local-key"  # Any string — local only, no real auth needed


def _find_hermes() -> str:
    """Find the hermes binary — check common locations."""
    import shutil
    # 1. In PATH
    found = shutil.which("hermes")
    if found:
        return found
    # 2. Common install locations
    for path in [
        "/usr/local/bin/hermes",
        "/root/.local/bin/hermes",
        "$HOME/.local/bin/hermes",
        "/data/data/com.termux/files/usr/bin/hermes",
        "/data/data/com.termux/files/home/.local/bin/hermes",
    ]:
        import os
        expanded = os.path.expandvars(path)
        if os.path.isfile(expanded):
            return expanded
    # 3. Try finding via python -m
    return "hermes"  # fallback — will error if not found


HERMES_CMD = _find_hermes()

# ── Models endpoint ─────────────────────────────────────────────────────
MODELS_RESPONSE = {
    "object": "list",
    "data": [
        {
            "id": "hermes",
            "object": "model",
            "created": 1700000000,
            "owned_by": "nous-research",
            "permission": [],
            "root": "hermes",
            "parent": None,
        }
    ],
}


def call_hermes(message: str, timeout: int = 300) -> str:
    """Send a message to Hermes and return the response."""
    import os
    env = {**os.environ, "HERMES_NONINTERACTIVE": "1"}
    # Ensure common bin dirs are in PATH for subprocess
    extra_paths = [
        os.path.expanduser("~/.local/bin"),
        "/usr/local/bin",
        "/data/data/com.termux/files/usr/bin",
    ]
    current_path = env.get("PATH", "")
    env["PATH"] = ":".join(extra_paths) + ":" + current_path
    try:
        result = subprocess.run(
            [HERMES_CMD, "-z", message],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        output = result.stdout.strip()
        if not output and result.stderr:
            return f"[Hermes error: {result.stderr.strip()[:500]}]"
        return output or "[No response from Hermes]"
    except subprocess.TimeoutExpired:
        return "[Hermes timed out — try a simpler request]"
    except FileNotFoundError:
        return "[Error: hermes command not found — is it installed and in PATH?]"
    except Exception as e:
        return f"[Error: {str(e)[:500]}]"


class HermesHandler(BaseHTTPRequestHandler):
    """HTTP handler — OpenAI-compatible chat completions API."""

    def log_message(self, format, *args):
        """Custom log format."""
        ts = time.strftime("%H:%M:%S")
        sys.stderr.write(f"[{ts}] {args[0]}\n")

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _check_auth(self) -> bool:
        """Accept any bearer token (local use only)."""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return True
        # Also accept x-api-key header (some apps use this)
        if self.headers.get("X-Api-Key"):
            return True
        # Accept no auth (local use)
        return True

    def do_OPTIONS(self):
        """CORS preflight."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Api-Key")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        # GET /v1/models
        if path == "/v1/models":
            self._send_json(200, MODELS_RESPONSE)
            return

        # GET /v1/model (some apps check this too)
        if path == "/v1/model":
            self._send_json(200, {
                "object": "model",
                "id": "hermes",
                "owned_by": "nous-research",
            })
            return

        # Health check
        if path in ("/health", "/"):
            self._send_json(200, {
                "status": "ok",
                "service": "hermes-api",
                "model": "hermes",
                "message": "Hermes Agent API is running",
            })
            return

        self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path

        # POST /v1/chat/completions — the main endpoint
        if path == "/v1/chat/completions":
            self._handle_chat_completions()
            return

        self._send_json(404, {"error": "Not found"})

    def _handle_chat_completions(self):
        if not self._check_auth():
            self._send_json(401, {"error": "Unauthorized"})
            return

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self._send_json(400, {"error": "Empty request body"})
            return

        try:
            body = json.loads(self.rfile.read(content_length))
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON"})
            return

        # Extract the last user message
        messages = body.get("messages", [])
        if not messages:
            self._send_json(400, {"error": "No messages provided"})
            return

        # Extract the last user message (handles both string and multimodal content)
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    user_message = content
                elif isinstance(content, list):
                    # Multimodal: extract text parts, skip images
                    parts = []
                    for part in content:
                        if isinstance(part, dict):
                            if part.get("type") == "text":
                                parts.append(part.get("text", ""))
                            elif part.get("type") == "image_url":
                                parts.append("[Image attached]")
                        elif isinstance(part, str):
                            parts.append(part)
                    user_message = " ".join(parts) if parts else "[Image only — no text]"
                break

        if not user_message:
            self._send_json(400, {"error": "No user message found"})
            return

        # Check for streaming request
        stream = body.get("stream", False)
        model = body.get("model", "hermes")
        request_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        if stream:
            self._handle_stream(user_message, request_id, model)
        else:
            self._handle_non_stream(user_message, request_id, model)

    def _handle_non_stream(self, user_message: str, request_id: str, model: str):
        """Non-streaming: call hermes, return full response."""
        print(f"📨 {user_message[:80]}...")

        response_text = call_hermes(user_message)

        print(f"🤖 {response_text[:80]}...")

        result = {
            "id": request_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response_text,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": len(user_message.split()),
                "completion_tokens": len(response_text.split()),
                "total_tokens": len(user_message.split()) + len(response_text.split()),
            },
        }

        self._send_json(200, result)

    def _handle_stream(self, user_message: str, request_id: str, model: str):
        """Streaming: send SSE chunks."""
        print(f"📨 [stream] {user_message[:80]}...")

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Send start chunk
        chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        }
        self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.flush()

        # Get response
        response_text = call_hermes(user_message)
        print(f"🤖 [stream] {response_text[:80]}...")

        # Send content chunks (word by word for streaming effect)
        words = response_text.split(" ")
        for i, word in enumerate(words):
            prefix = "" if i == 0 else " "
            chunk = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": prefix + word},
                        "finish_reason": None,
                    }
                ],
            }
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.flush()

        # Send end chunk
        chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main():
    parser = argparse.ArgumentParser(description="Hermes API Server")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Bind host (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Bind port (default: {DEFAULT_PORT})")
    parser.add_argument("--hermes-path", default=None, help="Full path to hermes binary (auto-detected if omitted)")
    args = parser.parse_args()

    global HERMES_CMD
    if args.hermes_path:
        HERMES_CMD = args.hermes_path

    print(f"🔍 Hermes binary: {HERMES_CMD}")
    server = HTTPServer((args.host, args.port), HermesHandler)

    print(f"""
╔══════════════════════════════════════════════════╗
║           🤖 Hermes API Server                  ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  URL:     http://{args.host}:{args.port}/v1        ║
║  Key:     {API_KEY:<37}║
║  Model:   hermes                                 ║
║                                                  ║
║  ChatBox Settings:                               ║
║  ┌──────────────────────────────────────────┐    ║
║  │ API URL: http://127.0.0.1:{args.port}/v1  │    ║
║  │ API Key: {API_KEY:<28} │    ║
║  │ Model:   hermes                          │    ║
║  └──────────────────────────────────────────┘    ║
║                                                  ║
║  Press Ctrl+C to stop                            ║
╚══════════════════════════════════════════════════╝
""")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        server.server_close()


if __name__ == "__main__":
    main()
