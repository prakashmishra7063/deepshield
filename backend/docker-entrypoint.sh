#!/bin/sh
# Hosting platforms (Render, Fly, Kubernetes) mount persistent disks owned by root.
# Fix ownership of the storage path, then run the server as the unprivileged user.
set -e
STORAGE="${DS_STORAGE_DIR:-/data/storage}"
if [ "$(id -u)" = "0" ]; then
    mkdir -p "$STORAGE"
    chown -R deepshield:deepshield "$(dirname "$STORAGE")" "$STORAGE" 2>/dev/null || true
    exec setpriv --reuid="$(id -u deepshield)" --regid="$(id -g deepshield)" --init-groups "$@"
fi
exec "$@"
