#!/usr/bin/env python3
"""Create a private CashStratum config from environment and launch CKPool solo mode."""
import json
import os
import pathlib
import subprocess
import sys

def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        raise SystemExit(2)
    return value

data_dir = pathlib.Path(os.environ.get("DATA_DIR", "/data"))
data_dir.mkdir(parents=True, exist_ok=True)
config_path = data_dir / "cashstratum.conf"

rpc_url = required("BCHN_RPC_URL")
rpc_user = required("BCHN_RPC_USER")
rpc_pass = required("BCHN_RPC_PASSWORD")
payout_address = required("BCH_PAYOUT_ADDRESS")
pool_fee = float(os.environ.get("POOL_FEE_PERCENT", "0"))
if not 0 <= pool_fee <= 100:
    raise SystemExit("POOL_FEE_PERCENT must be between 0 and 100")
if pool_fee != 0:
    print("WARNING: operator fee is not zero; review POOL_FEE_PERCENT.", file=sys.stderr)

notify = os.environ.get("BCHN_ZMQ_ENABLED", "true").lower() in ("1", "true", "yes", "on")
zmq_url = os.environ.get("BCHN_ZMQ_URL", "tcp://127.0.0.1:28332")
config = {
    "btcd": [{
        "url": rpc_url,
        "auth": rpc_user,
        "pass": rpc_pass,
        "notify": notify
    }],
    "bchaddress": payout_address,
    "pooladdress": payout_address,
    "poolfee": pool_fee,
    "btcsig": os.environ.get("COINBASE_TAG", "BCHN-SOLO"),
    "sockdir": "/tmp/bchn-solo",
    "blockpoll": int(os.environ.get("BLOCK_POLL_MS", "100")),
    "nonce1length": 4,
    "nonce2length": 8,
    "update_interval": int(os.environ.get("TEMPLATE_UPDATE_SECONDS", "30")),
    "serverurl": ["0.0.0.0:3333"],
    "mindiff": float(os.environ.get("MIN_SHARE_DIFFICULTY", "1")),
    "startdiff": float(os.environ.get("START_SHARE_DIFFICULTY", "42")),
    "maxdiff": 0,
    "logdir": str(data_dir / "logs")
}
if notify:
    config["zmqblock"] = zmq_url

config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
os.chmod(config_path, 0o600)
(pathlib.Path(data_dir) / "logs").mkdir(exist_ok=True)
print("Starting CKPool-derived CashStratum in solo mode on TCP 3333.")
print("RPC credentials are not printed. Verify the payout CashAddr before mining.")
os.execv("/usr/local/bin/ckpool", [
    "/usr/local/bin/ckpool", "-B", "-c", str(config_path),
    "-n", "bchn-solo", "-s", "/tmp/bchn-solo"
])
