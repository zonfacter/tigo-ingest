#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class NodeStats:
    node_id: str
    n: int
    rssi_mean: float | None
    rssi_min: int | None
    rssi_max: int | None
    rssi_p95: int | None


def run_influx(db: str, query: str) -> dict:
    p = subprocess.run(
        ["influx", "-database", db, "-format", "json", "-execute", query],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return json.loads(p.stdout)


def parse_series(obj: dict) -> list[NodeStats]:
    out: list[NodeStats] = []
    results = obj.get("results") or []
    for res in results:
        for series in res.get("series") or []:
            tags = series.get("tags") or {}
            node_id = str(tags.get("node_id") or "")
            cols = series.get("columns") or []
            vals = (series.get("values") or [[None]])[0]
            row = dict(zip(cols, vals, strict=False))
            out.append(
                NodeStats(
                    node_id=node_id,
                    n=int(row.get("n") or 0),
                    rssi_mean=(float(row["rssi_mean"]) if row.get("rssi_mean") is not None else None),
                    rssi_min=(int(row["rssi_min"]) if row.get("rssi_min") is not None else None),
                    rssi_max=(int(row["rssi_max"]) if row.get("rssi_max") is not None else None),
                    rssi_p95=(int(row["rssi_p95"]) if row.get("rssi_p95") is not None else None),
                )
            )
    return out


def fmt(x) -> str:
    if x is None:
        return "-"
    if isinstance(x, float):
        return f"{x:.1f}"
    return str(x)


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize Tigo RSSI stats per optimizer (node_id) from InfluxDB.")
    ap.add_argument("--db", default="bms")
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--measurement", default="tigo_power_report")
    ap.add_argument("--rp", default="autogen")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    q = (
        "SELECT count(\"rssi\") AS n, mean(\"rssi\") AS rssi_mean, "
        "min(\"rssi\") AS rssi_min, max(\"rssi\") AS rssi_max, percentile(\"rssi\",95) AS rssi_p95 "
        f'FROM "{args.rp}"."{args.measurement}" '
        f"WHERE time > now() - {args.hours}h GROUP BY \"node_id\""
    )

    try:
        raw = run_influx(args.db, q)
    except subprocess.CalledProcessError as e:
        print(e.stderr, file=sys.stderr)
        return 2

    stats = parse_series(raw)
    stats = [s for s in stats if s.node_id]
    if not stats:
        print("No data returned.")
        return 1

    print(f"Window: last {args.hours}h, measurement={args.rp}.{args.measurement}")
    print()
    print("Lowest report counts (often the real problem):")
    for s in sorted(stats, key=lambda x: x.n)[: args.top]:
        print(
            f"node_id={s.node_id:>3} n={s.n:>6} "
            f"rssi_mean={fmt(s.rssi_mean):>6} rssi_p95={fmt(s.rssi_p95):>4} "
            f"min={fmt(s.rssi_min):>4} max={fmt(s.rssi_max):>4}"
        )

    print()
    print("Highest mean RSSI:")
    for s in sorted(stats, key=lambda x: (x.rssi_mean is None, x.rssi_mean), reverse=True)[: args.top]:
        print(
            f"node_id={s.node_id:>3} n={s.n:>6} "
            f"rssi_mean={fmt(s.rssi_mean):>6} rssi_p95={fmt(s.rssi_p95):>4} "
            f"min={fmt(s.rssi_min):>4} max={fmt(s.rssi_max):>4}"
        )

    print()
    print("Lowest mean RSSI:")
    for s in sorted(stats, key=lambda x: (x.rssi_mean is None, x.rssi_mean))[: args.top]:
        print(
            f"node_id={s.node_id:>3} n={s.n:>6} "
            f"rssi_mean={fmt(s.rssi_mean):>6} rssi_p95={fmt(s.rssi_p95):>4} "
            f"min={fmt(s.rssi_min):>4} max={fmt(s.rssi_max):>4}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

