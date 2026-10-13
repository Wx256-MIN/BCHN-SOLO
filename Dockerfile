# BCHN-SOLO packages CashStratum, the BCH-specific CKPool-derived engine.
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

# Build CashStratum's maintained read-only monitoring API from the same pinned source.
FROM --platform=$BUILDPLATFORM golang:1.26.1-bookworm AS api-build
ARG TARGETARCH
WORKDIR /src/api
COPY --from=build /src/api /src/api
RUN mkdir -p /out \
    && CGO_ENABLED=0 GOOS=linux GOARCH=${TARGETARCH} go build -mod=vendor -trimpath -ldflags="-s -w" -o /out/cashstratum-api .

FROM debian:bookworm-slim AS runtime
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates libzmq5 python3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 1000 --home-dir /data --shell /usr/sbin/nologin pool

COPY --from=build /src/src/ckpool /usr/local/bin/ckpool
COPY --from=api-build /out/cashstratum-api /usr/local/bin/cashstratum-api
COPY docker/entrypoint.py /usr/local/bin/bchn-solo-entrypoint
COPY docker/api_entrypoint.py /usr/local/bin/bchn-solo-api-entrypoint
COPY docker/setup_server.py /usr/local/bin/bchn-solo-setup-server
COPY web/index.html /opt/www/index.html
COPY web/favicon.svg /opt/www/favicon.svg
RUN chmod 0755 /usr/local/bin/bchn-solo-entrypoint /usr/local/bin/bchn-solo-api-entrypoint /usr/local/bin/bchn-solo-setup-server \
    && mkdir -p /data /tmp/bchn-solo \
    && chown -R pool:pool /data /tmp/bchn-solo

ENV DATA_DIR=/data
EXPOSE 3333/tcp 8080/tcp 8888/tcp
VOLUME ["/data"]
USER pool
ENTRYPOINT ["python3", "/usr/local/bin/bchn-solo-entrypoint"]
