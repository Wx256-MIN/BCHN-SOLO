# BCHN porting checklist

This is an implementation checklist, not proof that the listed features are implemented.

## 1. Inventory upstream assumptions

- [ ] Map every Bitcoin RPC method used and confirm BCHN availability and semantics.
- [ ] Locate block-template model/types and coinbase assembly.
- [ ] Locate transaction and block serialization/hashing.
- [ ] Locate address decoding and payout script creation.
- [ ] Locate target/difficulty calculation, share validation, and block-candidate detection.
- [ ] Locate block-submission handling and parse BCHN rejection responses.
- [ ] Locate network constants and any Bitcoin-only dependencies.

## 2. BCH-specific implementation

- [ ] Use BCHN's template RPC on the correct BCH network.
- [ ] Confirm coinbase transaction serialization and extranonce layout match the Stratum implementation.
- [ ] Construct valid BCH output scripts from supported BCH mainnet/testnet/regtest addresses.
- [ ] Validate exact header/hash/target logic against BCHN-generated templates.
- [ ] Submit complete candidate blocks and record BCHN's exact response/rejection reason.
- [ ] Do not silently treat RPC errors, stale jobs, invalid shares, and rejected blocks as the same status.

## 3. Verification

- [ ] Unit tests for target conversion, serialization, address/script creation, and difficulty.
- [ ] Regtest integration: fetch template, build job, submit low-difficulty share, and test a known valid candidate.
- [ ] Negative tests: malformed submissions, duplicate shares, stale jobs, invalid extranonce, wrong network, RPC disconnect.
- [ ] Confirm node height/network identity before serving jobs.
- [ ] Test restart/reconnect behavior and ensure counters are not fabricated or double-counted.
- [ ] Do not label as mainnet-ready until block-candidate submission is verified against BCHN.

## 4. Operations/security

- [ ] RPC accessible only over a private network with strong credentials.
- [ ] Never publish RPC ports to the internet.
- [ ] Bind the web/API port to localhost or a trusted reverse proxy by default.
- [ ] Persist pool database/state.
- [ ] Add container healthcheck, graceful shutdown, restart behavior, and logs without secrets.
- [ ] Verify amd64/arm64 images and builds before advertising support.
