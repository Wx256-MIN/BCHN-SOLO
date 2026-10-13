#!/usr/bin/env python3
"""Create CashStratum config and start the CKPool-derived engine."""
import json
import os
import pathlib
import subprocess
import shutil
import sys
import time

def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        raise SystemExit(2)
    return value

data_dir = pathlib.Path(os.environ.get("DATA_DIR", "/data"))
data_dir.mkdir(parents=True, exist_ok=True)
config_path = data_dir / "cashstratum.conf"
settings_path = data_dir / "settings.json"
socket_dir = pathlib.Path("/tmp/bchn-solo")

payout_address = os.environ.get("BCH_PAYOUT_ADDRESS", "").strip()
if not payout_address:
    print("No BCH_PAYOUT_ADDRESS supplied; waiting for the payout address in the Umbrel setup page.")
    while not settings_path.exists():
        time.sleep(3)
    try:
        payout_address = json.loads(settings_path.read_text(encoding="utf-8")).get("payout_address", "").strip()
    except (OSError, ValueError, AttributeError):
        payout_address = ""
    if not payout_address:
        raise SystemExit("The saved payout address is empty or invalid; open the pool setup page and save a BCH CashAddr.")

rpc_url = required("BCHN_RPC_URL")
rpc_user = required("BCHN_RPC_USER")
rpc_pass = required("BCHN_RPC_PASSWORD")
pool_fee = float(os.environ.get("POOL_FEE_PERCENT", "0"))
if not 0 <= pool_fee <= 100:
    raise SystemExit("POOL_FEE_PERCENT must be between 0 and 100")
if pool_fee != 0:
    print("WARNING: operator fee is not zero; review POOL_FEE_PERCENT.", file=sys.stderr)

notify = os.environ.get("BCHN_ZMQ_ENABLED", "false").lower() in ("1", "true", "yes", "on")
zmq_url = os.environ.get("BCHN_ZMQ_URL", "tcp://127.0.0.1:28332")
btcd = {"url": rpc_url, "auth": rpc_user, "pass": rpc_pass, "notify": notify}
if notify:
    # CashStratum v1.2.4 reads each node's ZMQ endpoint from "zmqnotify".
    btcd["zmqnotify"] = zmq_url

config = {
    "btcd": [btcd],
    "bchaddress": payout_address,
    "pooladdress": payout_address,
    "poolfee": pool_fee,
    "btcsig": os.environ.get("COINBASE_TAG", "BCHN-SOLO"),
    "blockpoll": int(os.environ.get("BLOCK_POLL_MS", "100")),
    "nonce1length": 4,
    "nonce2length": 8,
    "update_interval": int(os.environ.get("TEMPLATE_UPDATE_SECONDS", "30")),
    "serverurl": ["0.0.0.0:3333"],
    # CashStratum parses both difficulty fields as JSON integers, not decimals.
    "mindiff": int(os.environ.get("MIN_SHARE_DIFFICULTY", "1")),
    "startdiff": int(os.environ.get("START_SHARE_DIFFICULTY", "42")),
    "maxdiff": 0,
    "logdir": str(data_dir / "logs")
}
config_temp = config_path.with_suffix(".tmp")
config_temp.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
os.chmod(config_temp, 0o600)
# Atomically publish the complete config so the monitoring API never reads a partial file.
config_temp.replace(config_path)
(data_dir / "logs").mkdir(exist_ok=True)

# Run CashStratum's own config parser before bringing up the live listener.
# This catches invalid types (including difficulty fields) without contacting BCHN.
check = subprocess.run(
    ["/usr/local/bin/ckpool", "-T", "-B", "-L", "-c", str(config_path),
     "-n", "bchn-solo", "-s", str(socket_dir)],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=15,
)
if check.returncode != 0:
    # Show the useful parser output while keeping payout address and RPC secrets private.
    details = check.stdout or ""
    for secret in (rpc_user, rpc_pass, payout_address):
        if secret:
            details = details.replace(secret, "[redacted]")
    if details.strip():
        print(details[-3000:], file=sys.stderr)
    print("CashStratum rejected its generated configuration.", file=sys.stderr)
    raise SystemExit(check.returncode or 1)

print("CashStratum configuration check passed.")

# Docker restart reuses the container's writable layer, so /tmp may retain
# main.pid and Unix sockets from a prior ckpool process that has already exited.
# This entrypoint is the new container PID 1; the prior pool process cannot
# survive a container restart. Remove only this private runtime socket directory.
if socket_dir.exists():
    print("Removing stale pool PID/socket files from the previous container run.")
    shutil.rmtree(socket_dir)

print("Starting CKPool-derived CashStratum in solo mode on TCP 3333 with share logging enabled.")
print("RPC credentials are not printed. Verify the payout CashAddr before mining.")
os.execv("/usr/local/bin/ckpool", [
    "/usr/local/bin/ckpool", "-B", "-L", "-c", str(config_path),
    "-n", "bchn-solo", "-s", "/tmp/bchn-solo"
])
