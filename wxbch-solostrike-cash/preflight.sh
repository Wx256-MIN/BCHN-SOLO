#!/usr/bin/env bash
# Safe pre-install checks for LoneStrike Cash (BCHN). Does not change pool or node data.
set -Eeuo pipefail

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
pass() { printf 'PASS: %s\n' "$*"; }

: "${APP_BITCOIN_CASH_NODE_NODE_IP:?Set BCHN node IP from Umbrel bitcoin-cash-node exports}"
: "${APP_BITCOIN_CASH_NODE_RPC_USER:?Set BCHN RPC username from Umbrel exports}"
: "${APP_BITCOIN_CASH_NODE_RPC_PASS:?Set BCHN RPC password from Umbrel exports}"

RPC_PORT="${APP_BITCOIN_CASH_NODE_RPC_PORT:-8332}"
ZMQ_PORT="${APP_BITCOIN_CASH_NODE_ZMQ_HASHBLOCK_PORT:-28332}"
NODE_IP="$APP_BITCOIN_CASH_NODE_NODE_IP"

command -v curl >/dev/null || fail "curl is required"
command -v docker >/dev/null || fail "Docker CLI is required"
command -v python3 >/dev/null || fail "python3 is required"

printf '%s\n' 'LoneStrike Cash preflight — read-only checks; no containers or data will be changed.'

images=(
  ghcr.io/danhaus93-ops/asicseer-pool:latest
  ghcr.io/danhaus93-ops/solostrike-cash-dashboard:latest
  ghcr.io/danhaus93-ops/bchn-sv2-bridge:latest
  ghcr.io/danhaus93-ops/lonestrike-sv2-pool:latest
)
for image in "${images[@]}"; do
  if docker buildx imagetools inspect "$image" >/dev/null 2>&1; then
    pass "Image manifest available: $image"
  else
    fail "Cannot inspect image manifest: $image (check network/registry access and tag)"
  fi
done

rpc_url="http://${NODE_IP}:${RPC_PORT}/"
rpc_response="$(curl --silent --show-error --max-time 5 --config /dev/fd/3 \
  --header 'content-type: text/plain;' --data-binary '{"jsonrpc":"1.0","id":"solostrike-preflight","method":"getblockchaininfo","params":[]}' \
  "$rpc_url" 3<<<"user = \"${APP_BITCOIN_CASH_NODE_RPC_USER}:${APP_BITCOIN_CASH_NODE_RPC_PASS}\"")" || fail "BCHN JSON-RPC request failed at ${NODE_IP}:${RPC_PORT}"

printf '%s' "$rpc_response" | python3 -c '
import json, sys
try:
    doc = json.load(sys.stdin)
    if doc.get("error"):
        raise ValueError("RPC returned an error")
    result = doc["result"]
    if result.get("chain") != "main":
        raise ValueError("Node is not on mainnet (chain=" + str(result.get("chain")) + ")")
    print("PASS: BCHN RPC authenticated; mainnet height=" + str(result.get("blocks")) +
          "; initialblockdownload=" + str(result.get("initialblockdownload")))
except Exception as exc:
    print("FAIL: BCHN RPC response invalid or unsuitable: " + str(exc), file=sys.stderr)
    sys.exit(1)
' || fail "BCHN RPC check failed"

if timeout 3 bash -c ":</dev/tcp/${NODE_IP}/${ZMQ_PORT}" 2>/dev/null; then
  pass "TCP connection to BCHN ZMQ port ${NODE_IP}:${ZMQ_PORT} succeeded (publisher topic/config still needs runtime confirmation)"
else
  fail "Cannot connect to BCHN ZMQ port ${NODE_IP}:${ZMQ_PORT}; verify BCHN publishes hashblock ZMQ on this port and allows access"
fi

printf '\n%s\n' 'Preflight passed. This verifies registry access, RPC authentication/mainnet response, and ZMQ TCP reachability only.'
printf '%s\n' 'It does NOT prove a share can be submitted or a block template accepted; keep the existing pool untouched until runtime mining tests pass.'
