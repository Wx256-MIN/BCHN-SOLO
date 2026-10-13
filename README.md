# BCHN-SOLO

**A self-hosted Bitcoin Cash solo-mining pool built on the CKPool lineage.**

This repository packages [CashStratum](https://github.com/cashstratum/cashstratum), an actively maintained BCH-specific CKPool fork, for a small, private, zero-fee solo pool using your existing Bitcoin Cash Node (BCHN). It is not a reimplementation of the mining protocol; the upstream C engine performs Stratum, job construction, share validation, and block submission.

## Current status

- Engine source pinned to CashStratum `v1.2.4` at image build time.
- **Main-branch image build and publish workflow succeeded** for `linux/amd64` and `linux/arm64`.
- The published image is intended to be available at `ghcr.io/wx256-min/bchn-solo:latest`. Verify that it can be pulled on your Umbrel before relying on it.
- CI verifies compilation and packaging only. BCHN regtest end-to-end testing (miner connection, share handling, and block-candidate submission) is still required before mainnet mining.
- A browser monitoring dashboard displays pool/node health, hashrate, workers/users, sampled accepted/rejected shares, and recent pool events. The private CashStratum operator API key stays server-side and the API listens only on the internal Docker network. The pool listens for Stratum V1 miners on TCP port `3333`.
- The pool preflights its generated config using CashStratum's parser, uses integer difficulty fields, places ZMQ at the BCHN node's `zmqnotify` field, and enables sharelog output for monitoring.

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
