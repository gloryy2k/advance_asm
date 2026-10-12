#!/usr/bin/env bash
set -euo pipefail
python -m backend.bootstrap
exec python -m backend.main
