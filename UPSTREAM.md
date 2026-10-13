# Upstream engine and design

BCHN-SOLO packages the BCH-specific CKPool-derived engine [CashStratum](https://github.com/cashstratum/cashstratum).

- Upstream source: https://github.com/cashstratum/cashstratum
- Pinned release: `v1.2.4` (see `ARG CASHSTRATUM_REF` in the Dockerfile)
- License: GPL-3.0-or-later; see [COPYING](COPYING)
- BCHN support: reference node in CashStratum's installation guide
- Miner protocol: Stratum V1 on TCP 3333
- Solo payout: miner CashAddr in the Stratum username
- Default operator fee: 0%

The upstream project implements the consensus-sensitive mining engine. This repository focuses on container packaging, configuration, and deployment. Do not describe a build as production-ready until the exact image passes a BCHN regtest mining test and its build logs are available.
