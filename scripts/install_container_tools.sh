#!/usr/bin/env bash
# Pinned release installer. Recon remains in the original vendor fork.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ARCH="${TARGETARCH:-$(uname -m)}"
case "$ARCH" in
    x86_64) ARCH=amd64 ;;
    aarch64) ARCH=arm64 ;;
esac
exec python "$SCRIPT_DIR/install_release_tools.py" \
    --arch "$ARCH" --destination "${BBASM_TOOLS_DEST:-/out}" "$@"
