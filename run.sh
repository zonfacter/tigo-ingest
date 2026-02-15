#!/usr/bin/env bash
set -euo pipefail

cd /home/black/tigo-ingest

while true; do
  # Ensure rustup-installed binaries are visible under systemd too.
  if [ -f "$HOME/.cargo/env" ]; then
    # shellcheck disable=SC1090
    . "$HOME/.cargo/env"
  fi

  if ! command -v taptap >/dev/null 2>&1; then
    echo "$(date -Is) ERROR: taptap not found in PATH. Install it (e.g. /usr/local/bin/taptap) then this service will continue." >&2
    sleep 300
    continue
  fi

  # If TAPTAP_CMD uses --tcp/--port, do a quick reachability check to avoid tight crash loops.
  if [ -f .env ]; then
    # Parse TAPTAP_CMD from the env file without sourcing (it can contain spaces).
    cmd_line="$(grep -E '^TAPTAP_CMD=' .env | head -n1 || true)"
    cmd_val="${cmd_line#TAPTAP_CMD=}"
    cmd_val="${cmd_val%$'\r'}"
    if [[ "$cmd_val" == \"*\" && "$cmd_val" == *\" ]]; then
      cmd_val="${cmd_val#\"}"
      cmd_val="${cmd_val%\"}"
    fi

    if [[ "$cmd_val" == *"--tcp "* || "$cmd_val" == *"--serial "* ]]; then
      # Use a placeholder for empty fields so `read` doesn't shift values.
      read -r ip port serial_dev < <(CMD="$cmd_val" python3 - <<'PY'
import os, shlex
cmd = os.environ.get("CMD", "")
args = shlex.split(cmd)
ip = "-"
port = "7160"
serial_dev = "-"
for i, a in enumerate(args):
    if a == "--tcp" and i + 1 < len(args):
        ip = args[i + 1]
    if a == "--port" and i + 1 < len(args):
        port = args[i + 1]
    if a == "--serial" and i + 1 < len(args):
        serial_dev = args[i + 1]
print(ip, port, serial_dev)
PY
)
      if [ "$ip" = "-" ]; then ip=""; fi
      if [ "$serial_dev" = "-" ]; then serial_dev=""; fi

      if [ -n "$serial_dev" ]; then
        if [ ! -e "$serial_dev" ]; then
          echo "$(date -Is) ERROR: serial device not found: $serial_dev (check wiring/USB and adjust TAPTAP_CMD)" >&2
          sleep 10
          continue
        fi
        echo "$(date -Is) INFO: serial device present: $serial_dev" >&2
      fi

      if [ -n "$ip" ] && [ -n "$port" ]; then
        echo "$(date -Is) INFO: precheck tcp $ip:$port" >&2
        if ! timeout 2 bash -c "</dev/tcp/$ip/$port" >/dev/null 2>&1; then
          echo "$(date -Is) ERROR: cannot connect to $ip:$port (connection refused/unreachable). Check TAP/RS485 bridge or use --serial." >&2
          sleep 60
          continue
        fi
        echo "$(date -Is) INFO: precheck tcp ok $ip:$port" >&2
      fi
    fi
  fi

  /home/black/tigo-ingest/.venv/bin/python -u -m tigo_ingest

  # If the ingest process exits (e.g. connection issue), wait a bit and retry.
  echo "$(date -Is) WARN: tigo_ingest exited, retrying in 10s" >&2
  sleep 10
done
