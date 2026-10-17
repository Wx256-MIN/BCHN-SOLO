# BCHN-SOLO — LoneStrike Cash

**A self-hosted Bitcoin Cash (BCH) solo-mining pool app for UmbrelOS, designed to use your existing Bitcoin Cash Node (BCHN).**

This repository currently packages **LoneStrike Cash (BCHN)** as an Umbrel community app. It includes Stratum V1 and Stratum V2 pool services plus a dashboard. It is intended to connect to the existing `bitcoin-cash-node` app rather than run a second BCH node.

> **Status and safety:** Repository packaging and configuration are not proof of successful live mining. Validate installation, BCHN connectivity, miner connections, share acceptance, and block submission before relying on it for mainnet mining. A share is not a block, and a block candidate is not a confirmed reward.

## What is included

- **Umbrel app ID:** `wxbch-solostrike-cash`
- **App name:** LoneStrike Cash (BCHN)
- **Stratum V1:** host TCP port `3335`
- **Stratum V2:** host TCP port `33333`
- **Dashboard:** served through the Umbrel app proxy on internal port `3000`
- **Node dependency:** existing Umbrel `bitcoin-cash-node` app
- **Persistent app data:** pool data/logs under `${APP_DATA_DIR}/data/pool` and SV2 data under `${APP_DATA_DIR}/data/sv2`

The app uses the upstream container images configured in `wxbch-solostrike-cash/docker-compose.yml`. Review those image sources and tags before updating them.

## Architecture

The Umbrel Compose package defines these services:

- **pool:** BCH pool engine, connected to BCHN RPC and ZMQ.
- **dashboard:** pool status, workers, shares, and block-event UI/API.
- **sv2-bridge:** bridge service connected to BCHN.
- **sv2-pool:** Stratum V2 endpoint.
- **app_proxy:** exposes the dashboard through Umbrel's app proxy.

The app uses the existing BCHN node's RPC endpoint on port `8332` and hash-block ZMQ endpoint on port `28332`, as supplied by Umbrel's app environment. If your BCHN installation uses different ports or settings, verify compatibility before installing.

## Install on UmbrelOS

1. Ensure the **Bitcoin Cash Node** app is installed, fully synced, and healthy.
2. In Umbrel, add this repository as a community app store if it is not already listed:
   `https://github.com/Wx256-MIN/BCHN-SOLO`
3. Find and install **LoneStrike Cash (BCHN)** (`wxbch-solostrike-cash`).
4. Open the app dashboard and verify that it can reach BCHN and that node/pool status is healthy.
5. Configure and verify your own BCH payout address using the controls supported by the installed app version before connecting a miner.
6. Confirm the miner connects and shares are accepted. Check the pool logs and BCHN directly for authoritative block and reward status.

If the app does not appear in the community store, check that the repository's root `umbrel-app-store.yml` and the app's `wxbch-solostrike-cash/umbrel-app.yml` are present on the default branch, then refresh/reload the store in Umbrel.

## Miner connection settings

Use the LAN address of your Umbrel host, not `localhost` on a separate miner.

| Setting | Stratum V1 | Stratum V2 |
| --- | --- | --- |
| Host TCP port | `3335` | `33333` |
| Pool URL example | `stratum+tcp://YOUR_UMBREL_LAN_IP:3335` | Depends on miner/client SV2 support and configuration |
| Payout | Verify the configured BCH payout address in the installed app | Verify the configured BCH payout address in the installed app |

Not all miners support Stratum V2. Use the protocol and connection format documented by your miner's firmware. Never use an example address as a payout address; verify that the configured address is yours and valid for BCH mainnet.

## BCHN requirements

- BCHN must be fully synchronized and able to serve block-template requests.
- RPC access must be available to the app through Umbrel's configured internal network.
- Do not expose BCHN RPC to the public internet.
- The app's Compose configuration expects hash-block ZMQ on port `28332`; verify that this endpoint is enabled and reachable in your BCHN setup.
- Do not assume `127.0.0.1` inside one container points to another container or to the Umbrel host.

## Data, upgrades, and removal

The app's persistent pool and SV2 data live under its own `${APP_DATA_DIR}/data` paths. Keep backups before app upgrades, reinstallations, or removal.

Removing source files from this GitHub repository does **not** uninstall an already installed Umbrel app or delete its persistent data. Conversely, deleting app data from Umbrel can be destructive; do not remove it unless you intend to erase the corresponding pool state and logs.

The former `wxbch-solo-pool/` package has been removed from the repository. The current app package is `wxbch-solostrike-cash/`.

## Security notes

- Never publish BCHN RPC credentials, wallet seeds, private keys, or passwords.
- Restrict RPC to the private network and only the services that require it.
- Treat public Stratum ports as untrusted network services. Prefer LAN or VPN access unless you have intentionally secured and exposed them.
- Verify payout address, node health, accepted shares, and actual block status independently. Dashboard events and logs alone are not proof of a confirmed block or payment.

## Repository layout

- `wxbch-solostrike-cash/umbrel-app.yml` — Umbrel app manifest.
- `wxbch-solostrike-cash/docker-compose.yml` — app service definitions, ports, dependencies, and persistent mounts.
- `wxbch-solostrike-cash/icon.svg` — app icon.
- `.github/workflows/solostrike-cash-preflight.yml` — package preflight checks.
- `umbrel-app-store.yml` — repository app-store metadata.

## Support and upstream

- Repository and issue tracker: https://github.com/Wx256-MIN/BCHN-SOLO
- App package: https://github.com/Wx256-MIN/BCHN-SOLO/tree/main/wxbch-solostrike-cash
- Upstream pool images are declared in `wxbch-solostrike-cash/docker-compose.yml`. Their behavior and availability are subject to their maintainers; review them before production use.
