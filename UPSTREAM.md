# Upstream and licensing

This project is intended as a derivative-work port of:

- Project: [benjamin-wilson/public-pool](https://github.com/benjamin-wilson/public-pool)
- Upstream description: TypeScript/NestJS Bitcoin Stratum mining server
- Upstream license file: [LICENSE.txt](https://github.com/benjamin-wilson/public-pool/blob/master/LICENSE.txt) (GPL-3.0)

The upstream repository has not yet been copied into this repository. Before distributing a derived build, import the relevant source and the complete upstream license/copyright notices, then document modifications. Do not claim this repository already contains the upstream implementation.

A correct BCHN port must review all Bitcoin-specific code paths, particularly RPC calls, block-template parsing, transaction/coinbase serialization, address decoding, proof-of-work target/hash handling, and candidate block submission. Configuration renaming alone is insufficient.
