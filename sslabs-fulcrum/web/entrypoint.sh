#!/bin/sh
set -eu

: "${NODE_HOST:?Missing Umbrel BCHN node address}"
: "${RPC_USER:?Missing Umbrel BCHN RPC user}"
: "${RPC_PASS:?Missing Umbrel BCHN RPC password}"

# Restrict substitution to our own template variables so Nginx variables
# such as $request_uri and $host remain intact.
export RPC_BASIC_AUTH="$(printf '%s' "${RPC_USER}:${RPC_PASS}" | base64 | tr -d '\n')"
envsubst '${NODE_HOST} ${RPC_BASIC_AUTH}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

exec nginx -g 'daemon off;'
