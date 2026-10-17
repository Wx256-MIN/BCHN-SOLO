#!/usr/bin/env python3
"""Umbrel setup page and read-only dashboard proxy for CashStratum's operator API."""
import json
import base64
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
from urllib.parse import urlencode, urlsplit
from cashaddr import is_valid_cashaddr

DATA_DIR = pathlib.Path(os.environ.get("DATA_DIR", "/data"))
SETTINGS = DATA_DIR / "settings.json"
ELECTRICITY_SETTINGS = DATA_DIR / "electricity-settings.json"
HISTORY_FILE = DATA_DIR / "hashrate-history.json"
HISTORY_LOCK = threading.Lock()
HISTORY_LIMIT = 1000
AGENT_PROPOSALS = DATA_DIR / "agent-proposals.json"
AGENT_LOCK = threading.Lock()
SHARE_COUNTERS = DATA_DIR / "share-counters.json"
API_KEY_FILE = DATA_DIR / "api.key"
WEB_ROOT = pathlib.Path("/opt/www")
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



def bchn_rpc_call(method, params=None):
    """Read-only BCHN JSON-RPC helper. Credentials are never returned to the browser."""
    host = os.environ.get("BCHN_RPC_URL", "").strip()
    user = os.environ.get("BCHN_RPC_USER", "")
    password = os.environ.get("BCHN_RPC_PASSWORD", "")
    if not host or not user or not password:
        return None, "BCHN RPC verification is not configured for the dashboard"
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    if not host.endswith("/"):
        host += "/"
    body = json.dumps({"jsonrpc": "1.0", "id": "bchn-solo-readonly", "method": method,
                       "params": params or []}).encode("utf-8")
    token = base64.b64encode((user + ":" + password).encode("utf-8")).decode("ascii")
    req = urllib.request.Request(host, data=body, headers={
        "Authorization": "Basic " + token, "Content-Type": "application/json",
        "Accept": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            result = json.loads(response.read(2_000_000).decode("utf-8"))
        if not isinstance(result, dict) or result.get("error"):
            return None, "BCHN RPC returned an error"
        return result.get("result"), None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError):
        return None, "BCHN RPC is unavailable or returned invalid data"


def _verify_block_events(events):
    """Cross-check log-derived block hashes against BCHN and calculate coinbase outputs."""
    verified = []
    seen = set()
    for event in events[:3]:
        block_hash = event.get("block_hash")
        if not isinstance(block_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", block_hash) or block_hash in seen:
            continue
        seen.add(block_hash)
        header, error = bchn_rpc_call("getblockheader", [block_hash, True])
        if error or not isinstance(header, dict):
            continue
        confirmations = header.get("confirmations")
        height = header.get("height")
        reward = None
        block, block_error = bchn_rpc_call("getblock", [block_hash, 1])
        if not block_error and isinstance(block, dict):
            txids = block.get("tx")
            if isinstance(txids, list) and txids:
                coinbase, coinbase_error = bchn_rpc_call("getrawtransaction", [txids[0], True, block_hash])
                if not coinbase_error and isinstance(coinbase, dict):
                    outputs = coinbase.get("vout", [])
                    try:
                        reward = round(sum(float(output["value"]) for output in outputs), 8)
                    except (KeyError, TypeError, ValueError):
                        reward = None
        verified.append({"block_hash": block_hash, "height": height,
                         "confirmations": confirmations if isinstance(confirmations, int) else None,
                         "chain_status": "active" if isinstance(confirmations, int) and confirmations > 0 else
                                         "not in active chain" if confirmations == -1 else "unknown",
                         "coinbase_output_bch": reward})
    return verified


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
        match = re.search(r"\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\]", line)
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
        hash_match = re.search(r"\b[0-9a-fA-F]{64}\b", line)
        block_hash = hash_match.group(0).lower() if hash_match else None
        safe_line = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b", "[redacted-ip]", line)
        safe_line = re.sub(r"bitcoincash:[qp][a-z0-9]{30,}", "bitcoincash:…", safe_line)
        events.append({"timestamp": timestamp, "result": result, "details": safe_line[:320], "block_hash": block_hash})
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
    lines = tail.get("lines") if isinstance(tail.get("lines"), list) else []
    pool_metrics = _pool_log_metrics(lines)
    share_state = share_tracker_snapshot()
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
            "accepted_difficulty": pool_metrics.get("accepted"),
            "rejected_difficulty": pool_metrics.get("rejected"),
            "bestshare": pool_metrics.get("bestshare"),
            "luck": pool_metrics.get("luck"),
        },
        "share_summary": {
            "sampled": len(share_state["shares"]),
            "scope": "tracked-since-start",
            "accepted": share_state["accepted"] if share_state["initialized"] else None,
            "rejected": share_state["rejected"] if share_state["initialized"] else None,
            "baseline_records": share_state["baseline_records"],
            "tracker_ready": share_state["initialized"],
            "tracking_started_at": share_state["started_at"],
            "last_checked_at": share_state["last_checked_at"],
            "tracker_error": share_state["error"],
        },
        "shares": share_state["shares"],
        "blocks": _safe_block_events(lines),\n        "verified_blocks": _verify_block_events(_safe_block_events(lines)),
        "activity": _safe_activity(lines),
        "errors": errors,
    }


_SHARE_LOCK = threading.Lock()
_SHARE_STATE = {
    "initialized": False,
    "cursor": None,
    "accepted": 0,
    "rejected": 0,
    "baseline_records": 0,
    "started_at": None,
    "last_checked_at": None,
    "shares": [],
    "error": None,
}


def _persist_share_state_locked():
    """Persist only privacy-safe share fields and the opaque API cursor."""
    data = {
        "initialized": _SHARE_STATE["initialized"],
        "cursor": _SHARE_STATE["cursor"],
        "accepted": _SHARE_STATE["accepted"],
        "rejected": _SHARE_STATE["rejected"],
        "baseline_records": _SHARE_STATE["baseline_records"],
        "started_at": _SHARE_STATE["started_at"],
        "last_checked_at": _SHARE_STATE["last_checked_at"],
        "shares": _SHARE_STATE["shares"][-20:],
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = SHARE_COUNTERS.with_suffix(".tmp")
    temp.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(SHARE_COUNTERS)


def _load_share_state():
    """Restore persistent counters so restarts do not zero tracked counts."""
    try:
        data = json.loads(SHARE_COUNTERS.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not data.get("initialized"):
            return
        cursor = data.get("cursor")
        if not isinstance(cursor, str):
            return
        accepted = max(0, int(data.get("accepted", 0)))
        rejected = max(0, int(data.get("rejected", 0)))
        baseline_records = max(0, int(data.get("baseline_records", 0)))
        records = data.get("shares") if isinstance(data.get("shares"), list) else []
        safe_records = []
        for share in records:
            if not isinstance(share, dict):
                continue
            result = share.get("result") if isinstance(share.get("result"), bool) else None
            safe_records.append({
                "timestamp": share.get("timestamp") if isinstance(share.get("timestamp"), int) else None,
                "worker": str(share.get("worker") or "default")[:48],
                "sdiff": share.get("sdiff"),
                "diff": share.get("diff"),
                "result": result,
                "reject_reason": str(share.get("reject_reason") or "")[:160],
            })
        with _SHARE_LOCK:
            _SHARE_STATE.update({
                "initialized": True,
                "cursor": cursor,
                "accepted": accepted,
                "rejected": rejected,
                "baseline_records": baseline_records,
                "started_at": data.get("started_at"),
                "last_checked_at": data.get("last_checked_at"),
                "shares": safe_records[-20:],
                "error": None,
            })
    except FileNotFoundError:
        return
    except (OSError, ValueError, TypeError) as exc:
        print(f"Share counter state could not be restored: {exc}", file=sys.stderr)


def share_tracker_snapshot():
    with _SHARE_LOCK:
        return {
            "initialized": _SHARE_STATE["initialized"],
            "cursor": _SHARE_STATE["cursor"],
            "accepted": _SHARE_STATE["accepted"],
            "rejected": _SHARE_STATE["rejected"],
            "baseline_records": _SHARE_STATE["baseline_records"],
            "started_at": _SHARE_STATE["started_at"],
            "last_checked_at": _SHARE_STATE["last_checked_at"],
            "shares": [dict(item) for item in _SHARE_STATE["shares"]],
            "error": _SHARE_STATE["error"],
        }


def _set_share_tracker_error(error):
    with _SHARE_LOCK:
        _SHARE_STATE["error"] = str(error or "Share data is temporarily unavailable")[:200]


def _poll_share_tracker():
    snapshot = share_tracker_snapshot()
    if not snapshot["initialized"]:
        payload, error = fetch_pool_api("/shares?limit=1000")
        if payload is None:
            _set_share_tracker_error(error)
            return
        cursor = payload.get("next_cursor")
        if not isinstance(cursor, str):
            _set_share_tracker_error("CashStratum /shares did not return a resume cursor")
            return
        raw_shares = payload.get("shares") if isinstance(payload.get("shares"), list) else []
        safe_shares = [_safe_share(item) for item in raw_shares if isinstance(item, dict)]
        now = int(time.time())
        with _SHARE_LOCK:
            if not _SHARE_STATE["initialized"]:
                # Count the individual records in this bootstrap sample, then add
                # each new record after the cursor. The snapshot is not lifetime history.
                baseline_accepted = sum(1 for item in safe_shares if item["result"] is True)
                baseline_rejected = sum(1 for item in safe_shares if item["result"] is False)
                _SHARE_STATE.update({
                    "initialized": True,
                    "cursor": cursor,
                    "accepted": baseline_accepted,
                    "rejected": baseline_rejected,
                    "baseline_records": len(safe_shares),
                    "started_at": now,
                    "last_checked_at": now,
                    "shares": list(reversed(safe_shares[-20:])),
                    "error": None,
                })
                _persist_share_state_locked()
        return

    cursor = snapshot["cursor"]
    if not isinstance(cursor, str):
        _set_share_tracker_error("Share tracker has no valid resume cursor")
        return
    query = urlencode({"since": cursor, "limit": 1000})
    payload, error = fetch_pool_api("/shares?" + query)
    if payload is None:
        _set_share_tracker_error(error)
        return
    next_cursor = payload.get("next_cursor")
    if not isinstance(next_cursor, str):
        _set_share_tracker_error("CashStratum /shares did not return a resume cursor")
        return
    raw_shares = payload.get("shares") if isinstance(payload.get("shares"), list) else []
    safe_shares = [_safe_share(item) for item in raw_shares if isinstance(item, dict)]
    now = int(time.time())
    with _SHARE_LOCK:
        if _SHARE_STATE["cursor"] != cursor:
            return
        if next_cursor == cursor and safe_shares:
            # Do not double-count if an upstream response violates cursor semantics.
            _SHARE_STATE["error"] = "Share API returned records without advancing its cursor"
            return
        _SHARE_STATE["last_checked_at"] = now
        _SHARE_STATE["error"] = None
        if next_cursor != cursor:
            _SHARE_STATE["cursor"] = next_cursor
            _SHARE_STATE["accepted"] += sum(1 for item in safe_shares if item["result"] is True)
            _SHARE_STATE["rejected"] += sum(1 for item in safe_shares if item["result"] is False)
            if safe_shares:
                _SHARE_STATE["shares"] = (list(reversed(safe_shares)) + _SHARE_STATE["shares"])[:20]
            _persist_share_state_locked()


def _share_tracker_loop():
    # 20 upstream requests/minute, below the CashStratum shares endpoint rate limit.
    while True:
        try:
            _poll_share_tracker()
        except Exception as exc:
            _set_share_tracker_error("Share tracker temporarily failed: " + str(exc))
        time.sleep(3)


def shares_snapshot():
    """Serve cached, sanitized data to the dashboard without re-querying CashStratum."""
    state = share_tracker_snapshot()
    return {
        "shares": state["shares"],
        "sampled": len(state["shares"]),
        "ready": state["initialized"],
        "last_checked_at": state["last_checked_at"],
        "tracking_started_at": state["started_at"],
        "baseline_records": state["baseline_records"],
        "error": state["error"],
    }, None


def _record_history(payload):
    """Persist bounded, privacy-safe hashrate and chain metric samples."""
    stats = payload.get("stats") or {}
    pool = payload.get("pool_metrics") or {}
    node = stats.get("node") or {}
    sample = {
        "timestamp": int(payload.get("generated_at") or time.time()),
        "hashrate": pool.get("hashrate1m") or stats.get("hashrate"),
        "hashrate5m": pool.get("hashrate5m"),
        "hashrate1hr": pool.get("hashrate1hr"),
        "workers": stats.get("workers"),
        "users": stats.get("users"),
        "block_height": stats.get("block_height") or node.get("blocks"),
        "network_difficulty": node.get("difficulty"),
        "best_share": pool.get("bestshare"),
        "accepted_difficulty": pool.get("accepted_difficulty"),
        "rejected_difficulty": pool.get("rejected_difficulty"),
    }
    with HISTORY_LOCK:
        rows = []
        try:
            loaded = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                rows = [row for row in loaded if isinstance(row, dict) and isinstance(row.get("timestamp"), int)]
        except (OSError, ValueError):
            pass
        # Replace same-second sample to avoid duplicates from concurrent dashboard requests.
        if rows and rows[-1].get("timestamp") == sample["timestamp"]:
            rows[-1] = sample
        else:
            rows.append(sample)
        rows = rows[-HISTORY_LIMIT:]
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            temp = HISTORY_FILE.with_suffix(".tmp")
            temp.write_text(json.dumps(rows, separators=(",", ":")) + "\n", encoding="utf-8")
            os.chmod(temp, 0o600)
            temp.replace(HISTORY_FILE)
        except OSError as exc:
            print(f"Could not persist metric history: {exc}", file=sys.stderr)


def history_snapshot():
    with HISTORY_LOCK:
        try:
            rows = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                rows = []
        except (OSError, ValueError):
            rows = []
    return {"samples": rows[-HISTORY_LIMIT:], "sample_count": min(len(rows), HISTORY_LIMIT),
            "retention_limit": HISTORY_LIMIT, "note": "History starts when this version runs; it is not retroactive."}


def dashboard_snapshot():
    now = time.monotonic()
    with _DASH_LOCK:
        if _DASH_CACHE["payload"] is not None and now < _DASH_CACHE["expires"]:
            return _DASH_CACHE["payload"]
        payload = _collect_dashboard()
        _record_history(payload)
        payload["history"] = history_snapshot()
        _DASH_CACHE["payload"] = payload
        _DASH_CACHE["expires"] = time.monotonic() + DASHBOARD_CACHE_SECONDS
        return payload


def agent_proposals_snapshot():
    with AGENT_LOCK:
        try:
            rows = json.loads(AGENT_PROPOSALS.read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                rows = []
        except (OSError, ValueError):
            rows = []
    return {"proposals": rows[-100:], "execution_enabled": False,
            "note": "Approval records proposals only. No pool, worker, configuration, or repository action is executed."}


def _save_agent_proposals(rows):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = AGENT_PROPOSALS.with_suffix(".tmp")
    temp.write_text(json.dumps(rows[-100:], separators=(",", ":")) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(AGENT_PROPOSALS)


class Handler(BaseHTTPRequestHandler):
    def route_path(self):
        # Accept paths with or without the Umbrel app URL prefix.
        path = urlsplit(self.path).path.rstrip("/") or "/"
        for suffix in ("/api/settings", "/api/dashboard", "/api/shares", "/api/electricity", "/api/history", "/api/agent/proposals", "/favicon.svg"):
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
        if path == "/api/electricity":
            settings = {"rate": None, "watts": None, "saved": False}
            try:
                stored = json.loads(ELECTRICITY_SETTINGS.read_text(encoding="utf-8"))
                rate, watts = stored.get("rate"), stored.get("watts")
                if isinstance(rate, (int, float)) and not isinstance(rate, bool) and 0 <= rate <= 100000:
                    settings["rate"] = rate
                if isinstance(watts, (int, float)) and not isinstance(watts, bool) and 0 <= watts <= 100000:
                    settings["watts"] = watts
                settings["saved"] = settings["rate"] is not None and settings["watts"] is not None
            except (OSError, ValueError, AttributeError):
                pass
            self.send_json(settings)
            return
        if path == "/api/history":
            self.send_json(history_snapshot())
            return
        if path == "/api/agent/proposals":
            self.send_json(agent_proposals_snapshot())
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
        path = self.route_path()
        if path == "/api/agent/proposals":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 8192:
                    raise ValueError("Invalid request size")
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                operation = body.get("operation", "create")
                if operation not in ("create", "approve", "reject"):
                    raise ValueError("Operation must be create, approve, or reject")
                with AGENT_LOCK:
                    try:
                        rows = json.loads(AGENT_PROPOSALS.read_text(encoding="utf-8"))
                        if not isinstance(rows, list):
                            rows = []
                    except (OSError, ValueError):
                        rows = []
                    if operation == "create":
                        kind = str(body.get("kind", "diagnostic"))[:32]
                        title = str(body.get("title", "")).strip()[:120]
                        detail = str(body.get("detail", "")).strip()[:1200]
                        proposal = str(body.get("proposal", "")).strip()[:2000]
                        allowed = {"diagnostic", "difficulty_change", "timeout_change", "worker_action", "code_fix", "block_verification"}
                        if kind not in allowed or not title or not detail or not proposal:
                            raise ValueError("A valid kind, title, evidence detail, and proposed next step are required")
                        proposal_id = str(int(time.time())) + "-" + os.urandom(4).hex()
                        rows.append({"id": proposal_id, "created_at": int(time.time()), "kind": kind,
                                     "title": title, "detail": detail, "proposal": proposal,
                                     "status": "pending", "execution": "disabled"})
                    else:
                        proposal_id = str(body.get("id", ""))[:80]
                        found = next((item for item in rows if item.get("id") == proposal_id), None)
                        if not found:
                            raise ValueError("Proposal not found")
                        if found.get("status") != "pending":
                            raise ValueError("Only pending proposals can be reviewed")
                        found["status"] = "approved" if operation == "approve" else "rejected"
                        found["reviewed_at"] = int(time.time())
                        found["execution"] = "disabled"
                    _save_agent_proposals(rows)
                self.send_json({"ok": True, "message": "Proposal recorded. Approval does not execute or apply a change.", **agent_proposals_snapshot()})
            except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self.send_json({"ok": False, "error": str(exc)}, 400)
            except OSError as exc:
                print(f"Could not save agent proposal: {exc}", file=sys.stderr)
                self.send_json({"ok": False, "error": "Cannot save proposal to app data."}, 500)
            return
        if path == "/api/electricity":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 4096:
                    raise ValueError("Invalid request size")
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                rate, watts = body.get("rate"), body.get("watts")
                if isinstance(rate, bool) or isinstance(watts, bool):
                    raise ValueError("Rate and watts must be numbers")
                rate, watts = float(rate), float(watts)
                if not (0 <= rate <= 100000 and 0 <= watts <= 100000):
                    raise ValueError("Rate and watts must be between 0 and 100,000")
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                temp = ELECTRICITY_SETTINGS.with_suffix(".tmp")
                temp.write_text(json.dumps({"rate": rate, "watts": watts}, separators=(",", ":")) + "\n", encoding="utf-8")
                os.chmod(temp, 0o600)
                temp.replace(ELECTRICITY_SETTINGS)
                self.send_json({"ok": True, "message": "Electricity settings saved to persistent app data."})
            except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self.send_json({"ok": False, "error": str(exc)}, 400)
            except OSError as exc:
                print(f"Could not save electricity settings: {exc}", file=sys.stderr)
                self.send_json({"ok": False, "error": "Cannot save electricity settings. Check app data directory permissions."}, 500)
            return
        if path != "/api/settings":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 4096:
                raise ValueError("Invalid request size")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            address = str(body.get("payout_address", "")).strip()
            if not is_valid_cashaddr(address):
                raise ValueError("Enter a valid mainnet BCH CashAddr, including its correct checksum, beginning with bitcoincash:q or bitcoincash:p.")
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
    _load_share_state()
    threading.Thread(target=_share_tracker_loop, name="share-history-tracker", daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
