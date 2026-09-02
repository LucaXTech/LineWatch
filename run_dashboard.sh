#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec ./.venv/bin/waitress-serve --listen=0.0.0.0:8080 dashboard:app
