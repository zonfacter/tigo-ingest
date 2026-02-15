#!/usr/bin/env bash
set -euo pipefail

cd /home/black/tigo-ingest

if [ -f "$HOME/.cargo/env" ]; then
  # shellcheck disable=SC1090
  . "$HOME/.cargo/env"
fi

cmd_line="$(grep -E '^TAPTAP_CMD=' .env | head -n1 || true)"
if [ -z "$cmd_line" ]; then
  echo "Missing TAPTAP_CMD in /home/black/tigo-ingest/.env" >&2
  exit 2
fi

cmd_val="${cmd_line#TAPTAP_CMD=}"
if [[ "$cmd_val" == \"*\" && "$cmd_val" == *\" ]]; then
  cmd_val="${cmd_val#\"}"
  cmd_val="${cmd_val%\"}"
fi

echo "TAPTAP_CMD=$cmd_val"
echo
echo "Running: $cmd_val (10s, first 20 lines)"
echo

timeout 10 bash -lc "$cmd_val" | head -n 20

