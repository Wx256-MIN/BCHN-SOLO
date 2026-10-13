# BCHN-SOLO builds CashStratum, the BCH-specific CKPool-derived mining engine.
# Pin the upstream release deliberately; review upstream changes before upgrading.
FROM debian:bookworm-slim AS build

ARG DEBIAN_FRONTEND=noninteractive
ARG CASHSTRATUM_REF=v1.2.4

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates git autoconf automake libtool pkg-config \
    yasm libzmq3-dev python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --depth 1 --branch "${CASHSTRATUM_REF}" \
    https://github.com/cashstratum/cashstratum.git /src

# Avoid -march=native: the image must be portable across AMD64 and ARM64.
RUN CFLAGS="-O2 -pipe" CXXFLAGS="-O2 -pipe" ./autogen.sh \
    && CFLAGS="-O2 -pipe" CXXFLAGS="-O2 -pipe" ./configure --disable-sv2 \
    && make -j2

FROM debian:bookworm-slim AS runtime
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates libzmq5 python3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --home-dir /data --shell /usr/sbin/nologin pool

COPY --from=build /src/src/ckpool /usr/local/bin/ckpool
COPY docker/entrypoint.py /usr/local/bin/bchn-solo-entrypoint
RUN chmod 0755 /usr/local/bin/bchn-solo-entrypoint \
    && mkdir -p /data /tmp/bchn-solo \
    && chown -R pool:pool /data /tmp/bchn-solo

ENV DATA_DIR=/data
EXPOSE 3333/tcp
VOLUME ["/data"]
USER pool
ENTRYPOINT ["python3", "/usr/local/bin/bchn-solo-entrypoint"]
