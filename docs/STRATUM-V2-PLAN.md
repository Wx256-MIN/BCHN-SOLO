# Stratum V2 compatibility plan

## Status

Planning only. This document does not claim that SV2 is implemented or active. The current BCHN-SOLO mining listener remains CashStratum Stratum V1 on TCP port 3333.

## Safe integration approach

1. **Choose BCH-compatible components.** Verify upstream maintenance, license, Bitcoin Cash transaction/template assumptions, Noise transport support, and a reproducible pinned image or source commit for both the Template Provider bridge and SV2 pool.
2. **Keep the current V1 path intact.** Add SV2 as separate services behind an opt-in Compose profile or separate app version. Do not replace the V1 pool image, listener, data directory, or payout configuration.
3. **Use private node access.** Reuse the existing BCHN RPC endpoint and credentials through environment variables/secrets. Never bake credentials into the repository, expose RPC to the public internet, or publish the operator API.
4. **Isolate persistence and ports.** Give SV2 its own persistent data subdirectory, health checks, restart policy, bounded logs, and documented ports. Avoid collisions with 3333 and Umbrel's app proxy.
5. **Prove regtest end-to-end.** Test template updates, miner/session authentication, share validation, stale-job handling, difficulty updates, block candidate submission, node restart, pool restart, and persistence. Confirm that an SV2-found block is accepted by BCHN before enabling mainnet use.
6. **Unify telemetry only after validation.** Add SV2 workers, best shares, accepted/rejected shares, and block events to the dashboard with protocol labels so V1 and V2 metrics are not double-counted.
7. **Gate activation.** Ship SV2 disabled by default. Document resource use and rollback. Require operator opt-in after tests pass.

## Acceptance criteria

- Existing V1 miners continue connecting on port 3333 during SV2 testing.
- SV2 services cannot access RPC credentials through the public web tier.
- A BCHN regtest solve can be submitted and confirmed through the SV2 path.
- Worker and share metrics are attributed to the correct protocol and survive service restarts where the upstream API supports it.
- The app remains installable on supported Umbrel architectures and does not rely on unpinned `latest` images for consensus-critical components.
