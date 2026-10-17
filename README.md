# BCHN-SOLO

**A self-hosted Bitcoin Cash solo-mining pool built on the CKPool lineage.**

This repository packages [CashStratum](https://github.com/cashstratum/cashstratum), an actively maintained BCH-specific CKPool fork, for a small, private, zero-fee solo pool using your existing Bitcoin Cash Node (BCHN). It is not a reimplementation of the mining protocol; the upstream C engine performs Stratum, job construction, share validation, and block submission.

## Current status

- Engine source pinned to CashStratum `v1.2.4` at image build time.
- **Main-branch image build and publish workflow succeeded** for `linux/amd64` and `linux/arm64`.
- The published image is intended to be available at `ghcr.io/wx256-min/bchn-solo:latest`. Verify that it can be pulled on your Umbrel before relying on it.
- CI verifies compilation and packaging only. BCHN regtest end-to-end testing (miner connection, share handling, and block-candidate submission) is still required before mainnet mining.
- A browser monitoring dashboard displays pool/node health, hashrate, workers/users, recent share records, persistent accepted/rejected share-record counts, recent pool events, and a block-found summary. Accepted/rejected counts count individual records from the initial `/shares` snapshot (up to 1,000 records) plus new records observed afterward; the API does not provide complete lifetime totals. The private CashStratum operator API key stays server-side and the API listens only on the internal Docker network. The pool listens for Stratum V1 miners on TCP port `3333`.
- The pool preflights its generated config using CashStratum's parser, uses integer difficulty fields, places ZMQ at the BCHN node's `zmqnotify` field, and enables sharelog output for monitoring. Failed preflight diagnostics are printed with the payout address and RPC credentials redacted. On container restart, the entrypoint removes only the non-persistent `/tmp/bchn-solo` runtime socket directory so stale `main.pid` files cannot block startup. The Docker build disables upstream CPU-feature auto-detection and uses portable SHA-256 code to avoid SIGILL/invalid-opcode crashes when deployed on older x86_64 or ARM64 CPUs.

## Features and defaults

- Solo mining: a miner's BCH CashAddr in the Stratum username is the payout destination.
- `POOL_FEE_PERCENT=0` by default.
- BCHN JSON-RPC for templates and block submission; optional BCHN ZMQ block notifications.
- Persistent data and logs under the Docker volume `/data`.
- Multi-architecture container build intended for `linux/amd64` and `linux/arm64`.
- Runs as an unprivileged container user.

## 1. Prepare BCHN

Your existing BCHN node must be fully synced and able to serve `getblocktemplate`. Configure authenticated RPC for the pool container and do not expose RPC to the public internet. If enabling ZMQ, configure BCHN to publish hash-block notifications and ensure the pool container can reach the configured ZMQ endpoint.

Do not assume `127.0.0.1` inside the pool container points to BCHN; it points to the pool container itself. Use a reachable node hostname or IP and the RPC port configured on your node.

## 2. Configure the pool

```sh
git clone https://github.com/Wx256-MIN/BCHN-SOLO.git
cd BCHN-SOLO
cp .env.example .env
```

Edit `.env` and set:
- `BCHN_RPC_URL`: BCHN RPC host and port, such as `192.168.1.20:8332`.
- `BCHN_RPC_USER` and `BCHN_RPC_PASSWORD`: the RPC credentials configured on your node.
- `BCH_PAYOUT_ADDRESS`: your own valid mainnet BCH CashAddr.
- `BCHN_ZMQ_ENABLED`: set to `true` only after ZMQ is configured and reachable; otherwise keep it `false`.
- Keep `POOL_FEE_PERCENT=0` for zero-fee solo mining.

Never commit `.env`. Use strong RPC credentials and restrict RPC to the private network.

## 3. Build and start

```sh
docker compose build
docker compose up -d
docker compose logs -f bchn-solo
```

The first build downloads the pinned CashStratum release source and compiles it inside the image. This requires internet access during the image build. To stop the pool:

```sh
docker compose down
```

The `/data` volume preserves configuration and logs across restarts.

## 4. Configure a miner

Use your Umbrel/BCHN host's LAN IP address (not `localhost`) and these settings:

| Miner field | Value |
| --- | --- |
| Pool URL | `stratum+tcp://YOUR_UMBREL_LAN_IP:3333` |
| Username | `bitcoincash:q...YOUR_VALID_CASHADDR[.worker]` |
| Password | `x` |

Use a valid BCH CashAddr that you control. Verify every character before connecting a miner: the solo pool builds the winning coinbase payout from the address supplied by the miner. A share is not a block, and a block candidate is not a reward until BCHN accepts it and consensus maturity requirements are met.

## UmbrelOS

The repository includes a community app-store package and a GHCR image publishing workflow. The Umbrel Compose app initializes shared `/data` permissions and a private operator API key, then runs the pool, read-only monitoring API, and setup/dashboard web server. The app still needs installation and runtime validation on an actual Umbrel device, followed by a BCHN regtest end-to-end test. Do not point mainnet miners at an untested image.

The Umbrel Compose file uses the official `bitcoin-cash-node` app's RPC endpoint on port `8332` and hash-block ZMQ endpoint on port `28332`. If your node is from a different community app store or uses custom ports, verify its connection settings before installation.

## Upstream and licensing

The mining engine is [CashStratum](https://github.com/cashstratum/cashstratum), derived from CKPool and licensed under GPL-3.0. See [UPSTREAM.md](UPSTREAM.md) and [COPYING](COPYING). The Dockerfile pins the upstream source tag; review upstream changes before changing that pin.

## Security notes

- Never publish BCHN RPC credentials or expose RPC to the internet.
- Do not commit `.env`, wallet seeds, private keys, or passwords.
- Check that the payout address belongs to you before mining.
- Treat a public Stratum port as an untrusted network service; use LAN/VPN access unless you intentionally harden and expose it.


## Feature parity additions (0.2.15)

- **Electricity cost calculator:** saves tariff per kWh and total rig watts separately from payout settings in persistent app data. Shows daily and 30-day kWh/cost estimates; it does not estimate mining revenue or profitability.
- **Worker share quality:** groups the currently retained recent share records by worker and shows accepted/rejected counts plus rejection percentage. This is a bounded recent sample, not lifetime worker totals.
- Existing BCHN node health, pool stats, Closest Strike comparison, block events, recent shares, and Stratum V1 connection settings remain in place. Stratum V2 is not part of this project.


### Operator diagnostics (0.2.17)

- **Read-only diagnostic checklist:** summarizes monitoring API availability, pool log presence, BCHN node metrics, sync state, share-tracker readiness and pool-stat availability.
- **Copy diagnostic report:** copies a sanitized JSON report for troubleshooting, with check status, guidance and API error summaries. It contains no RPC credentials and does not run repair actions.
- This is advisory only. Confirm node synchronization and block acceptance directly with BCHN. Runtime difficulty/timeout controls remain excluded until an authenticated, validated control interface and safe rollback behavior exist.

## Dashboard tools (0.2.16)

- **Configurable auto-refresh:** choose 5, 15, 30, or 60 seconds, or turn automatic refresh off.
- **Dashboard export:** export the current dashboard snapshot and retained recent shares as JSON for offline troubleshooting. The export contains the same sanitized dashboard fields shown in the UI.
- **Miner configuration copy:** copy a Stratum V1 connection template; replace the example Umbrel LAN address with your actual host address.
- **Share filters:** filter recent shares by worker name and accepted/rejected/unknown result without changing the underlying sample.
- **Event search:** search visible pool log events locally in the browser.
- **Worker last-seen estimate:** show the most recent timestamp found in the retained share sample per worker. This is not a live connection heartbeat and a connected but idle worker may not appear.
- **Block event history:** show up to ten recent block-related events parsed from available pool logs. Confirm accepted blocks and rewards with BCHN; log parsing is not independent chain verification.
- **Pool monitoring API uptime:** display the uptime value reported by the monitoring API process when available.

These are monitoring and operator convenience features. The dashboard intentionally does **not** change pool difficulty, worker timeout, payout rules, or mining-engine settings at runtime: the current app does not expose a validated authenticated control API for those actions, and adding cosmetic controls would be unsafe. Stratum V2 remains excluded.


## Metric history and troubleshooting proposals (0.2.19)

- **Persistent metric history:** dashboard snapshots save hashrate (pool-reported 1m/5m/1h where available), worker/user counts, chain height, network difficulty, best share, and accepted/rejected difficulty values. The history is bounded to the latest 1,000 samples in `/data/hashrate-history.json`; it begins after this version starts and is not retroactive. If metrics are unavailable, the history records unavailable values rather than fabricating data.
- **Hashrate chart and summary:** dashboard displays the retained hashrate trend, latest value, peak in the retained sample, network difficulty, and worker count. Pool hashrate units depend on CashStratum's returned metric format.
- **Rules-first troubleshooting proposals:** the dashboard can analyze available health, node, and share-tracker status and save evidence-based next steps to `/data/agent-proposals.json`. Operators can approve or reject a proposal; review status is recorded.
- **Safety boundary:** this release does not use an LLM provider and does not execute proposed commands or fixes. Approving a proposal records approval only; it does not change pool settings, worker connections, repository files, or running services. This prevents a misleading or unauthenticated dashboard control from silently changing a live mining pool.
- **Not yet included:** independently verified block confirmations/reward tracking via BCHN RPC; operational runtime difficulty/timeout controls; and actual worker management actions. These require additional BCHN/engine integration and a separately authenticated, validated action executor with rollback. Current block history remains log-derived and is not proof of a reward.
