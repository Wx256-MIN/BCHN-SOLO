#!/usr/bin/env python3
"""Tiny setup page for headless Umbrel installs; no dashboard or external dependencies."""
import json
import os
import pathlib
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA_DIR = pathlib.Path(os.environ.get("DATA_DIR", "/data"))
SETTINGS = DATA_DIR / "settings.json"
WEB_ROOT = pathlib.Path("/opt/www")
ADDRESS_RE = re.compile(r"^bitcoincash:[qp][a-z0-9]{41,}$")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/settings":
            address = ""
            try:
                address = json.loads(SETTINGS.read_text(encoding="utf-8")).get("payout_address", "")
            except (OSError, ValueError, AttributeError):
                pass
            payload = json.dumps({"configured": bool(address), "payout_address": address}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        body = (WEB_ROOT / "index.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'self'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/settings":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 4096:
                raise ValueError("Invalid request size")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            address = str(body.get("payout_address", "")).strip()
            if not ADDRESS_RE.fullmatch(address):
                raise ValueError("Enter a mainnet BCH CashAddr beginning with bitcoincash:q or bitcoincash:p.")
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            temp = SETTINGS.with_suffix(".tmp")
            temp.write_text(json.dumps({"payout_address": address}, indent=2) + "\n", encoding="utf-8")
            os.chmod(temp, 0o600)
            temp.replace(SETTINGS)
            payload = json.dumps({"ok": True, "message": "Address saved. The pool will start shortly."}).encode()
            self.send_response(200)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            payload = json.dumps({"ok": False, "error": str(exc)}).encode()
            self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        # Avoid writing form data or addresses to access logs.
        return

if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
