#!/bin/bash
set -euo pipefail
if [ ! -s /data/configdb/replica.key ]; then
  umask 077
  openssl rand -base64 756 > /data/configdb/replica.key
fi
chown mongodb:mongodb /data/configdb/replica.key
chmod 400 /data/configdb/replica.key
exec /usr/local/bin/docker-entrypoint.sh "$@"
