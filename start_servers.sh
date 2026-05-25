#!/bin/bash
set -euo pipefail

if command -v sentinelrouter >/dev/null 2>&1; then
  exec sentinelrouter
fi

exec go run ./cmd/sentinelrouter
