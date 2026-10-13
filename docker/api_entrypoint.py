#!/usr/bin/env python3
"""Load the private API key and start CashStratum's read-only operator API."""
import os
import pathlib
import sys
import time

data_dir = pathlib.Path(os.environ.get("DATA_DIR", "/data"))
conf = data_dir / "cashstratum.conf"
key_file = data_dir / "api.key"

# The pool creates its config only after the operator saves a payout address.
while not conf.is_file():
    print("Waiting for BCHN-SOLO pool configuration before starting monitoring API.", flush=True)
    time.sleep(2)

try:
    api_key = key_file.read_text(encoding="utf-8").strip()
except OSError as exc:
    print(f"Cannot read private monitoring API key: {exc}", file=sys.stderr)
    raise SystemExit(2)

if len(api_key) < 64 or any(ch not in "0123456789abcdef" for ch in api_key.lower()):
    print("Private monitoring API key is missing or invalid.", file=sys.stderr)
    raise SystemExit(2)

os.environ["CASHSTRATUM_API_KEY"] = api_key
os.environ.setdefault("CASHSTRATUM_LOG_PATH", str(data_dir / "logs" / "bchn-solo.log"))
os.environ.setdefault("CASHSTRATUM_USER_LOGS_PATH", str(data_dir / "logs" / "users"))
os.environ.setdefault("CASHSTRATUM_CONF_PATH", str(conf))
os.environ.setdefault("CASHSTRATUM_API_PORT", "8888")
os.execv("/usr/local/bin/cashstratum-api", ["/usr/local/bin/cashstratum-api"])
