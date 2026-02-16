#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def parse_last_point_time(raw_json: str) -> datetime | None:
    try:
        obj = json.loads(raw_json)
    except Exception:
        return None

    results = obj.get("results") or []
    for res in results:
        series = res.get("series") or []
        for s in series:
            cols = s.get("columns") or []
            vals = s.get("values") or []
            if not vals:
                continue
            row = dict(zip(cols, vals[0], strict=False))
            ts = row.get("time")
            if not ts:
                continue
            if isinstance(ts, (int, float)):
                # Influx json default precision can be ns epoch.
                return datetime.fromtimestamp(float(ts) / 1_000_000_000, tz=timezone.utc)
            if isinstance(ts, str):
                if ts.endswith("Z"):
                    ts = ts[:-1] + "+00:00"
                return datetime.fromisoformat(ts).astimezone(timezone.utc)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Health-check for tigo-ingest + Influx writes")
    ap.add_argument("--service", default="tigo-ingest.service")
    ap.add_argument("--db", default="bms")
    ap.add_argument("--rp", default="autogen")
    ap.add_argument("--measurement", default="tigo_power_report")
    ap.add_argument("--max-lag-min", type=int, default=240, help="Fail if latest point is older than this")
    args = ap.parse_args()

    status = run(["systemctl", "is-active", args.service])
    if status.returncode != 0 or status.stdout.strip() != "active":
        print(f"CRIT service_not_active service={args.service} state={status.stdout.strip()!r}")
        return 2

    q = f'SELECT last("power_w") FROM "{args.rp}"."{args.measurement}"'
    influx = run(["influx", "-database", args.db, "-format", "json", "-execute", q])
    if influx.returncode != 0:
        print(f"CRIT influx_query_failed rc={influx.returncode} err={influx.stderr.strip()!r}")
        return 2

    last_ts = parse_last_point_time(influx.stdout)
    if last_ts is None:
        print("CRIT no_points_found")
        return 2

    now = datetime.now(timezone.utc)
    lag_min = (now - last_ts).total_seconds() / 60.0
    if lag_min > args.max_lag_min:
        print(f"CRIT stale_data lag_min={lag_min:.1f} max_lag_min={args.max_lag_min} last_ts_utc={last_ts.isoformat()}")
        return 2

    print(f"OK lag_min={lag_min:.1f} last_ts_utc={last_ts.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
