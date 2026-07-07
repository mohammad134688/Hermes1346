#!/usr/bin/env python3
"""
Hermes Chat Bridge Server
=========================
Runs in Termux (NOT PRoot). Accepts HTTP requests from the Android app
and forwards them to Hermes inside proot-distro Ubuntu.

Usage:
  python3 hermes_bridge.py                    # Default port 8765
  python3 hermes_bridge.py --port 8765        # Custom port
  python3 hermes_bridge.py --proot-user root  # PRoot user (default: root)

Requirements:
  - Termux with Python 3
  - proot-distro with Ubuntu installed
  - Hermes Agent installed inside Ubuntu

Start:
  nohup python3 hermes_bridge.py > ~/hermes_bridge.log 2>&1 &
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
COMMAND_TIMEOUT = 180  # 3 minutes max per hermes command

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(os.path.expanduser("~"), "hermes_bridge.log"), encoding="utf-8"),
    ],
)
log = logging.getLogger("hermes-bridge")

# ─── Session Management ──────────────────────────────────────────────────────

class SessionManager:
    """Manages Hermes session IDs for conversation continuity."""

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
        """Build the hermes chat command."""
        # Escape message for shell
        escaped_msg = message.replace("'", "'\\''")

        if session_id:
            # Resume existing session
            cmd = (
                f"proot-distro login {self.distro} "
                f"--user {self.user} "
                f"-- bash -c 'cd {self.work_dir} && "
                f"hermes chat -Q -q \"{escaped_msg}\" "
                f"--resume {session_id} 2>/dev/null'"
            )
        else:
            # New session
            cmd = (
                f"proot-distro login {self.distro} "
                f"--user {self.user} "
                f"-- bash -c 'cd {self.work_dir} && "
                f"hermes chat -Q -q \"{escaped_msg}\" 2>/dev/null'"
            )
        return cmd

    def _extract_session_id(self, output: str) -> str:
        """Try to extract session ID from hermes output."""
        # Hermes sometimes outputs session info, try to find it
        # Pattern: "Session: xxxxxxxx" or "session_id: xxxxxxxx"
        patterns = [
            r"[Ss]ession[_ ]?[Ii][Dd]?[:\s]+([a-zA-Z0-9_]+)",
            r"Session\s+([a-zA-Z0-9_]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                return match.group(1)
        return ""

    def chat(self, message: str, session_id: str = "") -> dict:
        """Send a message to Hermes and return the response."""
        cmd = self._build_command(message, session_id)
        log.info(f"Executing: hermes chat (session={session_id or 'new'})")

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT,
            )

            output = result.stdout.strip()
            stderr = result.stderr.strip()

            if result.returncode != 0 and stderr:
                log.warning(f"Hermes stderr: {stderr[:200]}")

            # Try to extract session ID from output
            new_session_id = self._extract_session_id(output)

            # Clean up output - remove ANSI codes and hermes-specific formatting
            cleaned = self._clean_output(output)

            return {
                "response": cleaned,
                "session_id": new_session_id or session_id,
                "success": True,
                "error": None,
            }

        except subprocess.TimeoutExpired:
            log.error("Hermes command timed out")
            return {
                "response": "",
                "session_id": session_id,
                "success": False,
                "error": "timeout",
            }
        except Exception as e:
            log.error(f"Execution error: {e}")
            return {
                "response": "",
                "session_id": session_id,
                "success": False,
                "error": str(e),
            }

    def _clean_output(self, text: str) -> str:
        """Remove ANSI escape codes and clean up hermes output."""
        # Remove ANSI codes
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        cleaned = ansi_escape.sub('', text)

        # Remove common hermes artifacts
        lines = cleaned.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Skip empty lines at start/end
            if not stripped and not cleaned_lines:
                continue
            cleaned_lines.append(line)

        # Remove trailing empty lines
        while cleaned_lines and not cleaned_lines[-1].strip():
            cleaned_lines.pop()

        return '\n'.join(cleaned_lines).strip()

    def status(self) -> bool:
        """Check if hermes is accessible."""
        try:
            cmd = (
                f"proot-distro login {self.distro} "
                f"--user {self.user} "
                f"-- bash -c 'cd {self.work_dir} && hermes --version 2>/dev/null'"
            )
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=15
            )
            return result.returncode == 0
        except Exception:
            return False


# ─── Threaded HTTP Server ────────────────────────────────────────────────────

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """HTTPServer that handles each request in a new thread."""
    daemon_threads = True

# ─── HTTP Handler ────────────────────────────────────────────────────────────

class ChatHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the chat API."""

    executor: HermesExecutor  # Set by main()

    def log_message(self, format, *args):
        """Override to use our logger."""
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
        elif self.path == "/new":
            self._handle_new_session()
        else:
            self._send_json({"error": "not found"}, 404)

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self._add_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _handle_chat(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            message = body.get("message", "").strip()
            session_id = body.get("session_id", "")

            if not message:
                self._send_json({"error": "empty message"}, 400)
                return

            log.info(f"Chat request: session={session_id or 'new'}, len={len(message)}")

            # Execute
            result = self.executor.chat(message, session_id)

            # Update session
            if result["success"] and result["session_id"]:
                sessions.save_session(result["session_id"])

            self._send_json(result)

        except json.JSONDecodeError:
            self._send_json({"error": "invalid json"}, 400)
        except Exception as e:
            log.error(f"Chat handler error: {e}")
            self._send_json({"error": str(e)}, 500)

    def _handle_new_session(self):
        session_id = sessions.new_session_id()
        sessions.save_session(session_id)
        self._send_json({
            "session_id": session_id,
            "success": True,
        })

    def _handle_status(self):
        is_online = self.executor.status()
        self._send_json({
            "status": "online" if is_online else "offline",
            "hermes": is_online,
        })

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
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--proot-distro", default=DEFAULT_PROOT_DISTRO, help="PRoot distro name")
    parser.add_argument("--proot-user", default=DEFAULT_PROOT_USER, help="PRoot user")
    parser.add_argument("--work-dir", default=HERMES_WORK_DIR, help="Hermes working directory")
    args = parser.parse_args()

    # Create executor
    executor = HermesExecutor(
        distro=args.proot_distro,
        user=args.proot_user,
        work_dir=args.work_dir,
    )
    ChatHandler.executor = executor

    # Quick health check
    log.info("Checking Hermes availability...")
    if executor.status():
        log.info("✅ Hermes is accessible")
    else:
        log.warning("⚠️  Hermes may not be accessible. Check proot-distro setup.")

    # Start server
    server = ThreadedHTTPServer((args.host, args.port), ChatHandler)
    log.info(f"🚀 Hermes Bridge running on http://{args.host}:{args.port}")
    log.info(f"   Distro: {args.proot_distro}, User: {args.proot_user}")
    log.info(f"   Work dir: {args.work_dir}")
    log.info(f"   Timeout: {COMMAND_TIMEOUT}s per command")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
