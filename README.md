# BCHN-SOLO — LoneStrike Cash

**A self-hosted Bitcoin Cash (BCH) solo-mining pool app for UmbrelOS, designed to use your existing Bitcoin Cash Node (BCHN).**

This repository packages LoneStrike Cash as an Umbrel community app and includes a separate optional `sslabs-fulcrum` Electrum server package. Fulcrum is a wallet/indexing service, not a mining pool, and uses the existing `bitcoin-cash-node` app rather than launching another node.

> **Status and safety:** Repository packaging and configuration are not proof of successful live mining or successful Fulcrum indexing. Validate installation, BCHN connectivity, miner connections, share acceptance, indexing progress, and wallet connections on Umbrel before relying on either app.

## Apps in this repository

### LoneStrike Cash (BCHN)

- **Umbrel app ID:** `wxbch-solostrike-cash`
- **Stratum V1:** host TCP port `3335`
- **Stratum V2:** host TCP port `33333`
- **Dashboard:** internal port `3000`
- **Node dependency:** existing Umbrel `bitcoin-cash-node` app
- **Persistent data:** `${APP_DATA_DIR}/data/pool` and `${APP_DATA_DIR}/data/sv2`

### Fulcrum (BCH)

- **Umbrel app ID:** `sslabs-fulcrum`
- **Purpose:** Electrum server for Bitcoin Cash wallets; it indexes the existing BCHN node.
- **Dashboard:** app proxy to the web service on internal port `80`
- **Electrum TCP:** host port `50021`
- **Electrum SSL:** host port `50022`
- **Node dependency:** existing Umbrel `bitcoin-cash-node` app
- **Persistent data:** `${APP_DATA_DIR}/data/fulcrum`, including the index database and TLS certificate/key.

Fulcrum's runtime configuration is generated from the Umbrel-provided `APP_BITCOIN_CASH_NODE_*` settings. Do not add real RPC credentials to tracked files. If credentials previously committed to a public repository were real, rotate them; deleting a secret from the latest file does not erase it from Git history.

## Architecture and BCHN requirements

LoneStrike Cash defines a pool engine, dashboard, SV2 bridge, and SV2 pool. Fulcrum defines a separate Fulcrum service, a one-shot configuration initializer, and a lightweight Nginx status page. Neither package should launch a second BCHN node.

Both packages use Umbrel's BCHN connection settings. BCHN must be fully synchronized, RPC must be available to the app over Umbrel's private app network, and hash-block ZMQ must be enabled and reachable by the mining pool. Do not expose BCHN RPC to the public internet.

Fulcrum's first index build can take a long time and use substantial disk space. Keep its persistent app data when upgrading, and back it up before reinstalling or removing the app.

## Install on UmbrelOS

1. Ensure the official **Bitcoin Cash Node** app is installed, fully synced, and healthy.
2. Add this repository as a community app store if it is not already listed: `https://github.com/Wx256-MIN/BCHN-SOLO`.
3. Install LoneStrike Cash for mining, or install Fulcrum separately for Electrum wallet connectivity.
4. Verify each app's logs and status. For Fulcrum, wait for indexing to finish and test an Electrum wallet against `YOUR_UMBREL_LAN_IP:50022` (SSL) or port `50021` (TCP).
5. For mining, verify your BCH payout address, miner connection, accepted shares, and actual block status independently.

The Fulcrum configuration changes in the compatibility branch are not yet runtime-verified on Umbrel. Do not assume installation or indexing success until tested on the target device.

## Miner connection settings

Use your Umbrel host's LAN IP rather than `localhost` from a separate miner.

| Setting | Stratum V1 | Stratum V2 |
| --- | --- | --- |
| Host TCP port | `3335` | `33333` |
| Pool URL example | `stratum+tcp://YOUR_UMBREL_LAN_IP:3335` | Depends on miner/client SV2 support |

Not all miners support Stratum V2. Follow the protocol and connection format documented by the miner firmware. Never use an example address as a payout address.

## Security and data

- Never publish BCHN RPC credentials, wallet seeds, private keys, or passwords.
- If a real RPC password was committed publicly, rotate it even after removing it from the current file.
- Keep BCHN RPC private and restricted to the services that need it.
- Removing source files from this repository does not uninstall an app or delete Umbrel's persistent app data.
- Do not delete app data unless you intend to erase the corresponding index, pool state, or logs.

## Repository layout

- `wxbch-solostrike-cash/umbrel-app.yml` — mining pool manifest.
- `wxbch-solostrike-cash/docker-compose.yml` — pool, dashboard, and SV2 services.
- `sslabs-fulcrum/umbrel-app.yml` — Fulcrum manifest.
- `sslabs-fulcrum/docker-compose.yml` — Fulcrum, config initializer, and dashboard services.
- `sslabs-fulcrum/web/` — Nginx dashboard and proxy configuration.
- `umbrel-app-store.yml` — repository app-store metadata.

## Support and upstream

- Repository and issue tracker: https://github.com/Wx256-MIN/BCHN-SOLO
- Fulcrum upstream: https://github.com/cculianu/Fulcrum
- The container images and tags are declared in each app's Compose file. Review upstream image sources and behavior before production use.
