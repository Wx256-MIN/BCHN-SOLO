# BCHN-SOLO

A work-in-progress effort to adapt [Public Pool](https://github.com/benjamin-wilson/public-pool) for Bitcoin Cash Node (BCHN) and UmbrelOS.

> **Status: scaffolding only — not ready for mining.** This package contains deployment guidance and configuration templates. The upstream Public Pool code uses Bitcoin-specific RPC, transaction, address, and proof-of-work assumptions. Do not connect miners to this project until those paths have been deliberately ported and tested against BCHN.

## Goals

- Preserve upstream GPL-3.0 licensing and attribution when importing upstream source.
- Connect to an existing BCHN node through authenticated RPC.
- Use BCH-compatible block templates, coinbase construction, address handling, proof-of-work validation, and block submission.
- Support Stratum V1 ASICs and accurate accepted/rejected/stale share accounting.
- Package the service for UmbrelOS via Docker with persistent data and health checks.

## Architecture plan

1. **Node adapter:** BCHN RPC configuration, chain/network identity checks, ZMQ block notifications (if enabled), timeouts and reconnects.
2. **BCH consensus layer:** verify BCH network rules and mining serialization; do not assume Bitcoin block templates or coinbase serialization are interchangeable.
3. **Stratum:** handle miner sessions, jobs, share difficulty, validation, duplicate/stale share classification, and candidate block submission via BCHN RPC.
4. **Observability:** pool health, node height, workers, accepted/rejected/stale shares, and useful rejection reasons.
5. **Umbrel:** non-root container, env-file configuration, state volume, restart policy, and documented RPC networking.

## Safety and current limitations

- This repository is not yet a functioning or audited pool.
- Do not expose BCHN RPC to the public internet. Prefer a private Docker network or LAN, strong RPC credentials, and firewall rules.
- Scope `rpcallowip` only to the pool's actual network; do not copy broad subnet examples blindly.
- Never commit a real `.env`, RPC password, wallet private key, TLS private key, or other secret.
- An accepted share is not a block; a submitted candidate still needs BCHN acceptance.
- Mainnet mining must not be attempted before regtest testing verifies template parsing, coinbase construction, share validation, and block submission.

## Development

The first milestone is to port and test the upstream code—not just rename `BITCOIN_*` environment variables. See [UPSTREAM.md](UPSTREAM.md) and [docs/BCHN_PORTING.md](docs/BCHN_PORTING.md).

## License

The upstream project is GPL-3.0. Any distributed derivative must retain the applicable license and required notices. See [LICENSE-STATUS.md](LICENSE-STATUS.md) for current import status.
