#!/usr/bin/env python3
"""Umbrel setup page and read-only dashboard proxy for CashStratum's operator API."""
import json
import os
import pathlib
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

DATA_DIR = pathlib.Path(os.environ.get("DATA_DIR", "/data"))
SETTINGS = DATA_DIR / "settings.json"
API_KEY_FILE = DATA_DIR / "api.key"
WEB_ROOT = pathlib.Path("/opt/www")
ADDRESS_RE = re.compile(r"^bitcoincash:[qp][a-z0-9]{41,}$")
POOL_API = "http://api:8888"
DASHBOARD_CACHE_SECONDS = 12
_DASH_LOCK = threading.Lock()
_DASH_CACHE = {"expires": 0.0, "payload": None}


def fetch_pool_api(path):
    """Fetch authenticated engine metrics over the private Docker network."""
    try:
        key = API_KEY_FILE.read_text(encoding="utf-8").strip()
        if not key:
            return None, "Monitoring API key is empty"
        req = urllib.request.Request(
            POOL_API + path,
            headers={"Authorization": "Bearer " + key, "Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=2.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                return None, "Monitoring API returned an unexpected response"
            return payload, None
    except urllib.error.HTTPError as exc:
        return None, f"Monitoring API returned HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, "Monitoring API is starting or unavailable"
    except (ValueError, UnicodeDecodeError):
        return None, "Monitoring API returned invalid JSON"


def _pool_log_metrics(lines):
    metrics = {}
    for line in reversed(lines):
        match = re.search(r"Pool:(\{.*\})", line)
        if not match:
            continue
        try:
            obj = json.loads(match.group(1))
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            for key, value in obj.items():
                metrics.setdefault(key, value)
        if "hashrate1m" in metrics and "accepted" in metrics and "rejected" in metrics:
            break
    return metrics


def _safe_activity(lines):
    keywords = (
        "BLOCK ACCEPTED", "BLOCK REJECTED", "Solved and confirmed block",
        "Possible block solve", "Network diff set", "ERROR", "WARNING",
        "Failed", "failed", "RPC", "authoris", "share", "bitcoind",
        "no bitcoinds", "server alive", "block template", "template",
        "getblocktemplate", "connected to live server", "bound serverurl",
        "network diff", "critical", "reject",
    )
    selected = []
    for line in reversed(lines):
        if not any(word.lower() in line.lower() for word in keywords):
            continue
        line = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b", "[redacted-ip]", line)
        line = re.sub(r"bitcoincash:[qp][a-z0-9]{30,}", "bitcoincash:…", line)
        selected.append(line[:320])
        if len(selected) >= 15:
            break
    return selected



def _safe_block_events(lines):
    """Return recent block-solve/submission events parsed from pool logs."""
    markers = (
        "block accepted", "block rejected", "possible block solve",
        "solved and confirmed block", "block candidate", "submitblock",
        "block found", "block solved", "submitted block",
    )
    events = []
    for line in reversed(lines):
        low = line.lower()
        if not any(marker in low for marker in markers):
            continue
        timestamp = None
        match = re.search(r"\\[(\\d{4}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?)\\]", line)
        if match:
            timestamp = match.group(1)
        if "reject" in low or "failed" in low:
            result = "Rejected"
        elif "accept" in low or "confirmed" in low:
            result = "Accepted"
        elif "possible" in low or "candidate" in low or "found" in low or "solved" in low:
            result = "Candidate"
        else:
            result = "Submitted"
        safe_line = re.sub(r"\\b(?:\\d{1,3}\\.){3}\\d{1,3}(?::\\d+)?\\b", "[redacted-ip]", line)
        safe_line = re.sub(r"bitcoincash:[qp][a-z0-9]{30,}", "bitcoincash:…", safe_line)
        events.append({"timestamp": timestamp, "result": result, "details": safe_line[:320]})
        if len(events) >= 50:
            break
    return events

def _safe_share(share):
    createdate = str(share.get("createdate", ""))
    try:
        timestamp = int(createdate.split(",", 1)[0])
    except (ValueError, TypeError):
        timestamp = None
    worker = str(share.get("worker", "") or "default")
    # Only send the worker suffix and share result to the browser. Do not send IP,
    # payout username, user agent, or other connection-identifying fields.
    return {
        "timestamp": timestamp,
        "worker": worker[:48],
        "sdiff": share.get("sdiff"),
        "diff": share.get("diff"),
        "result": share.get("result") if isinstance(share.get("result"), bool) else None,
        "reject_reason": str(share.get("reject-reason") or "")[:160],
    }


def _collect_dashboard():
    paths = {
        "health": "/health",
        "stats": "/stats",
        "tail": "/tail?lines=120",
        "shares": "/shares?limit=100",
    }
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {name: executor.submit(fetch_pool_api, path) for name, path in paths.items()}
        results = {name: future.result() for name, future in futures.items()}

    data, errors = {}, {}
    for name, (payload, error) in results.items():
        if payload is not None:
            data[name] = payload
        if error:
            errors[name] = error

    health = data.get("health") or {}
    stats = data.get("stats") or {}
    tail = data.get("tail") or {}
    share_data = data.get("shares") or {}
    lines = tail.get("lines") if isinstance(tail.get("lines"), list) else []
    pool_metrics = _pool_log_metrics(lines)
    shares = share_data.get("shares") if isinstance(share_data.get("shares"), list) else []
    safe_shares = [_safe_share(s) for s in shares if isinstance(s, dict)]
    counted = [s for s in safe_shares if s["result"] is not None]
    # CashStratum's /stats endpoint does not expose cumulative accepted and
    # rejected share counters. Its Pool log records do expose accepted/rejected
    # metrics, but on a fresh process those may still be zero while older share
    # records remain in the API. Prefer explicit log counters when they are
    # present and non-zero; otherwise show counts from the API's recent sample
    # rather than rendering blank cards. The sample size is returned separately
    # so the UI can disclose when it is showing sampled rather than round totals.
    def _counter(value):
        try:
            number = int(float(value))
            return max(0, number)
        except (TypeError, ValueError, OverflowError):
            return None

    log_accepted = _counter(pool_metrics.get("accepted"))
    log_rejected = _counter(pool_metrics.get("rejected"))
    sample_accepted = sum(1 for share in counted if share["result"] is True)
    sample_rejected = sum(1 for share in counted if share["result"] is False)
    has_log_counters = (log_accepted is not None and log_rejected is not None
                        and (log_accepted > 0 or log_rejected > 0))
    if has_log_counters:
        accepted, rejected = log_accepted, log_rejected
        counter_source = "pool-log"
    else:
        accepted, rejected = sample_accepted, sample_rejected
        counter_source = "recent-sample"
    api_up = bool(health) and health.get("status") == "ok"
    log_exists = bool(health.get("log_exists"))
    if api_up and log_exists and stats:
        status = "online"
    elif api_up:
        status = "starting"
    else:
        status = "unavailable"

    return {
        "generated_at": int(time.time()),
        "status": status,
        "health": {
            "api_up": api_up,
            "log_exists": log_exists,
            "log_size": health.get("log_size"),
            "uptime": health.get("uptime"),
        },
        "stats": {
            "hashrate": stats.get("hashrate"),
            "workers": stats.get("workers"),
            "users": stats.get("users"),
            "transactions": stats.get("transactions"),
            "block_height": stats.get("block_height"),
            "node": stats.get("node"),
        },
        "pool_metrics": {
            "hashrate1m": pool_metrics.get("hashrate1m"),
            "hashrate5m": pool_metrics.get("hashrate5m"),
            "hashrate1hr": pool_metrics.get("hashrate1hr"),
            "accepted_diff": pool_metrics.get("accepted"),
            "rejected_diff": pool_metrics.get("rejected"),
            "bestshare": pool_metrics.get("bestshare"),
            "luck": pool_metrics.get("luck"),
        },
        "share_summary": {
            "sampled": len(counted),
            "scope": counter_source,
            "accepted": accepted,
            "rejected": rejected,
        },
        "shares": safe_shares[-20:][::-1],
        "blocks": _safe_block_events(lines),
        "activity": _safe_activity(lines),
        "errors": errors,
    }


def shares_snapshot():
    """Return only sanitized recent share data for the one-second table refresh."""
    payload, error = fetch_pool_api("/shares?limit=100")
    if payload is None:
        return None, error or "Share data is temporarily unavailable"
    shares = payload.get("shares") if isinstance(payload.get("shares"), list) else []
    safe_shares = [_safe_share(share) for share in shares if isinstance(share, dict)]
    counted = [share for share in safe_shares if share["result"] is not None]
    return {"shares": safe_shares[-20:][::-1], "sampled": len(counted)}, None


def dashboard_snapshot():
    now = time.monotonic()
    with _DASH_LOCK:
        if _DASH_CACHE["payload"] is not None and now < _DASH_CACHE["expires"]:
            return _DASH_CACHE["payload"]
        payload = _collect_dashboard()
        _DASH_CACHE["payload"] = payload
        _DASH_CACHE["expires"] = time.monotonic() + DASHBOARD_CACHE_SECONDS
        return payload


class Handler(BaseHTTPRequestHandler):
    def route_path(self):
        # Accept paths with or without the Umbrel app URL prefix.
        path = urlsplit(self.path).path.rstrip("/") or "/"
        for suffix in ("/api/settings", "/api/dashboard", "/api/shares", "/favicon.svg"):
            if path.endswith(suffix):
                return suffix
        if path.endswith("/index.html"):
            return "/index.html"
        if path == "/" or path.endswith("/wxbch-solo-pool"):
            return "/"
        if re.fullmatch(r"/[A-Za-z0-9_-]+", path):
            return "/"
        return path

    def send_json(self, payload, status=200):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.route_path()
        if path == "/api/settings":
            address = ""
            try:
                address = json.loads(SETTINGS.read_text(encoding="utf-8")).get("payout_address", "")
            except (OSError, ValueError, AttributeError):
                pass
            self.send_json({"configured": bool(address), "payout_address": address})
            return
        if path == "/api/shares":
            payload, error = shares_snapshot()
            if payload is None:
                self.send_json({"error": error or "Share data is temporarily unavailable"}, 503)
            else:
                self.send_json(payload)
            return
        if path == "/api/dashboard":
            try:
                self.send_json(dashboard_snapshot())
            except Exception as exc:
                print(f"Dashboard collection failed: {exc}", file=sys.stderr)
                self.send_json({"status": "unavailable", "errors": {"dashboard": "Dashboard data is temporarily unavailable."}}, 200)
            return
        if path == "/favicon.svg":
            try:
                body = (WEB_ROOT / "favicon.svg").read_bytes()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path not in ("/", "/index.html"):
            self.send_error(404)
            return
        body = (WEB_ROOT / "index.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'self'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.route_path() != "/api/settings":
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
            self.send_json({"ok": True, "message": "Address saved. The pool will start shortly."})
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.send_json({"ok": False, "error": str(exc)}, 400)
        except OSError as exc:
            print(f"Could not save payout settings: {exc}", file=sys.stderr)
            self.send_json({"ok": False, "error": "Cannot write payout settings. Check the app data directory permissions and restart BCHN-SOLO."}, 500)

    def log_message(self, fmt, *args):
        # Avoid writing payout addresses or request details to logs.
        return


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
