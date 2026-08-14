#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m tc_ai_bridge "$@"
