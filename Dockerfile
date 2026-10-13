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

# Do not let configure select SHA-NI, AVX, SSE4 or ARM crypto code based on
# the CI/build machine's /proc/cpuinfo. This image must run on older CPUs too.
# Replace CashStratum's host-CPU auto-detection block with portable C fallback
# conditionals before autoreconf regenerates ./configure.
RUN python3 - <<'PY'
from pathlib import Path

path = Path("/src/configure.ac")
source = path.read_text()
start_marker = "x86_shani=\\nrorx=\\navx1=\\nsse4=\\nsha2=\\n"
end_marker = "AM_CONDITIONAL([HAVE_ARM_SHA2], [test x$sha2 = xsha2])"
start = source.find(start_marker)
if start < 0:
    raise SystemExit("Cannot locate CashStratum CPU feature detection block")
end = source.find(end_marker, start)
if end < 0:
    raise SystemExit("Cannot locate end of CashStratum CPU feature detection block")
end += len(end_marker)
replacement = """# BCHN-SOLO portable build: disable builder-dependent CPU-specific implementations.
x86_shani=
rorx=
avx1=
sse4=
sha2=
AM_CONDITIONAL([HAVE_X86_SHANI], [false])
AM_CONDITIONAL([HAVE_AVX2], [false])
AM_CONDITIONAL([HAVE_AVX1], [false])
AM_CONDITIONAL([HAVE_SSE4], [false])
AM_CONDITIONAL([HAVE_ARM_SHA2], [false])"""
path.write_text(source[:start] + replacement + source[end:])
PY

# Keep compiler flags generic and deliberately build with the portable SHA-256 implementation.
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
