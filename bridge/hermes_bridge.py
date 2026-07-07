#!/usr/bin/env python3
"""
Hermes Chat Bridge Server (with Streaming)
============================================
Runs in Termux (NOT PRoot). Accepts HTTP requests from the Android app
and forwards them to Hermes inside proot-distro Ubuntu.

Supports:
  - POST /chat      → One-shot (wait for full response)
  - POST /chat/stream → SSE streaming (real-time chunks)
  - GET  /status    → Server status
  - GET  /health    → Health check
  - POST /new       → New session

Usage:
  python3 hermes_bridge.py                    # Default port 8765
  python3 hermes_bridge.py --port 8765        # Custom port
  python3 hermes_bridge.py --proot-distro ubuntu  # PRoot distro
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path

# ─── Configuration ───────────────────────────────────────────────────────────

DEFAULT_PORT = 8765
DEFAULT_PROOT_USER = "root"
DEFAULT_PROOT_DISTRO = "ubuntu"
HERMES_WORK_DIR = "/root"
COMMAND_TIMEOUT = 180

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(os.path.expanduser("~"), "hermes_bridge.log"),
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger("hermes-bridge")

# ─── Session Management ──────────────────────────────────────────────────────

class SessionManager:
    def __init__(self):
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()

    def get_session(self, session_id: str) -> dict | None:
        with self._lock:
            return self._sessions.get(session_id)

    def save_session(self, session_id: str, title: str = ""):
        with self._lock:
            self._sessions[session_id] = {
                "title": title,
                "last_used": time.time(),
            }

    def new_session_id(self) -> str:
        return f"hermeschat_{int(time.time() * 1000)}"

sessions = SessionManager()

# ─── Hermes Executor ─────────────────────────────────────────────────────────

class HermesExecutor:
    """Executes hermes commands inside proot-distro."""

    def __init__(self, distro: str, user: str, work_dir: str):
        self.distro = distro
        self.user = user
        self.work_dir = work_dir

    def _build_command(self, message: str, session_id: str = "") -> str:
        escaped_msg = message.replace("'", "'\\''")
        if session_id:
            cmd = (
                f"proot-distro login {self.distro} "
                f"--user {self.user} "
                f"-- bash -c 'cd {self.work_dir} && "
                f"hermes -z \"{escaped_msg}\" --resume {session_id}'"
            )
        else:
            cmd = (
                f"proot-distro login {self.distro} "
                f"--user {self.user} "
                f"-- bash -c 'cd {self.work_dir} && "
                f"hermes -z \"{escaped_msg}\"'"
            )
        return cmd

    def _extract_session_id(self, output: str) -> str:
        patterns = [
            r"[Ss]ession[_ ]?[Ii][Dd]?[:\s]+([a-zA-Z0-9_]+)",
            r"Session\s+([a-zA-Z0-9_]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                return match.group(1)
        return ""

    def _clean_output(self, text: str) -> str:
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        cleaned = ansi_escape.sub('', text)
        lines = cleaned.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped and not cleaned_lines:
                continue
            cleaned_lines.append(line)
        while cleaned_lines and not cleaned_lines[-1].strip():
            cleaned_lines.pop()
        return '\n'.join(cleaned_lines).strip()

    def chat(self, message: str, session_id: str = "") -> dict:
        """One-shot: wait for full response."""
        cmd = self._build_command(message, session_id)
        log.info(f"Chat (one-shot): session={session_id or 'new'}, len={len(message)}")

        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=COMMAND_TIMEOUT,
            )
            output = result.stdout.strip()
            stderr = result.stderr.strip()

            log.info(f"Exit: {result.returncode}, stdout: {len(output)}, stderr: {len(stderr)}")
            if stderr:
                log.warning(f"stderr: {stderr[:300]}")

            new_session_id = self._extract_session_id(output)
            cleaned = self._clean_output(output)

            return {
                "response": cleaned,
                "session_id": new_session_id or session_id,
                "success": True,
                "error": None,
            }
        except subprocess.TimeoutExpired:
            log.error("Hermes timed out")
            return {"response": "", "session_id": session_id, "success": False, "error": "timeout"}
        except Exception as e:
            log.error(f"Error: {e}")
            return {"response": "", "session_id": session_id, "success": False, "error": str(e)}

    def chat_stream(self, message: str, session_id: str = ""):
        """
        Streaming generator: yields chunks as they come.
        Uses Popen to read stdout line by line.
        """
        cmd = self._build_command(message, session_id)
        log.info(f"Chat (stream): session={session_id or 'new'}, len={len(message)}")

        try:
            process = subprocess.Popen(
                cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )

            full_response = []
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

            # Read stdout line by line
            for line in process.stdout:
                line = line.rstrip('\n')
                # Clean ANSI codes
                clean_line = ansi_escape.sub('', line)
                if clean_line:
                    full_response.append(clean_line)
                    yield {"type": "chunk", "text": clean_line}

            process.wait(timeout=COMMAND_TIMEOUT)

            stderr = process.stderr.read().strip()
            if stderr:
                log.warning(f"Stream stderr: {stderr[:300]}")

            full_text = '\n'.join(full_response).strip()
            new_session_id = self._extract_session_id(full_text)
            cleaned = self._clean_output(full_text)

            log.info(f"Stream done: {len(cleaned)} chars, exit={process.returncode}")

            yield {
                "type": "done",
                "response": cleaned,
                "session_id": new_session_id or session_id,
                "success": process.returncode == 0,
                "error": None if process.returncode == 0 else f"exit_code_{process.returncode}",
            }

        except subprocess.TimeoutExpired:
            log.error("Stream timed out")
            process.kill()
            yield {"type": "done", "response": "", "session_id": session_id,
                   "success": False, "error": "timeout"}
        except Exception as e:
            log.error(f"Stream error: {e}")
            yield {"type": "done", "response": "", "session_id": session_id,
                   "success": False, "error": str(e)}

    def status(self) -> bool:
        try:
            cmd = (
                f"proot-distro login {self.distro} "
                f"--user {self.user} "
                f"-- bash -c 'cd {self.work_dir} && hermes --version 2>/dev/null'"
            )
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
            return result.returncode == 0
        except Exception:
            return False


# ─── Threaded HTTP Server ────────────────────────────────────────────────────

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

# ─── HTTP Handler ────────────────────────────────────────────────────────────

class ChatHandler(BaseHTTPRequestHandler):
    executor: HermesExecutor

    def log_message(self, format, *args):
        log.info(f"{self.client_address[0]} - {format % args}")

    def do_GET(self):
        if self.path == "/status":
            self._handle_status()
        elif self.path == "/health":
            self._send_json({"status": "ok"})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/chat":
            self._handle_chat()
        elif self.path == "/chat/stream":
            self._handle_chat_stream()
        elif self.path == "/new":
            self._handle_new_session()
        else:
            self._send_json({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self._add_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length))

    def _handle_chat(self):
        try:
            body = self._read_body()
            message = body.get("message", "").strip()
            session_id = body.get("session_id", "")

            if not message:
                self._send_json({"error": "empty message"}, 400)
                return

            result = self.executor.chat(message, session_id)
            if result["success"] and result["session_id"]:
                sessions.save_session(result["session_id"])
            self._send_json(result)

        except json.JSONDecodeError:
            self._send_json({"error": "invalid json"}, 400)
        except Exception as e:
            log.error(f"Chat error: {e}")
            self._send_json({"error": str(e)}, 500)

    def _handle_chat_stream(self):
        """SSE streaming endpoint."""
        try:
            body = self._read_body()
            message = body.get("message", "").strip()
            session_id = body.get("session_id", "")

            if not message:
                self._send_json({"error": "empty message"}, 400)
                return

            # Send SSE headers
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self._add_cors_headers()
            self.end_headers()

            # Stream chunks
            for chunk in self.executor.chat_stream(message, session_id):
                event_type = chunk.get("type", "chunk")
                data = json.dumps(chunk, ensure_ascii=False)
                self.wfile.write(f"event: {event_type}\ndata: {data}\n\n".encode("utf-8"))
                self.wfile.flush()

                # Save session when done
                if event_type == "done" and chunk.get("session_id"):
                    sessions.save_session(chunk["session_id"])

            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        except json.JSONDecodeError:
            self._send_json({"error": "invalid json"}, 400)
        except Exception as e:
            log.error(f"Stream error: {e}")
            try:
                self.wfile.write(f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n".encode())
                self.wfile.flush()
            except Exception:
                pass

    def _handle_new_session(self):
        session_id = sessions.new_session_id()
        sessions.save_session(session_id)
        self._send_json({"session_id": session_id, "success": True})

    def _handle_status(self):
        is_online = self.executor.status()
        self._send_json({"status": "online" if is_online else "offline", "hermes": is_online})

    def _send_json(self, data: dict, code: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._add_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _add_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Hermes Chat Bridge Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--proot-distro", default=DEFAULT_PROOT_DISTRO)
    parser.add_argument("--proot-user", default=DEFAULT_PROOT_USER)
    parser.add_argument("--work-dir", default=HERMES_WORK_DIR)
    args = parser.parse_args()

    executor = HermesExecutor(
        distro=args.proot_distro,
        user=args.proot_user,
        work_dir=args.work_dir,
    )
    ChatHandler.executor = executor

    log.info("Checking Hermes availability...")
    if executor.status():
        log.info("✅ Hermes is accessible")
    else:
        log.warning("⚠️  Hermes may not be accessible. Check proot-distro setup.")

    server = ThreadedHTTPServer((args.host, args.port), ChatHandler)
    log.info(f"🚀 Hermes Bridge running on http://{args.host}:{args.port}")
    log.info(f"   Endpoints: POST /chat | POST /chat/stream | GET /status")
    log.info(f"   Distro: {args.proot_distro}, User: {args.proot_user}")
    log.info(f"   Timeout: {COMMAND_TIMEOUT}s per command")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down...")
        server.shutdown()

if __name__ == "__main__":
    main()
