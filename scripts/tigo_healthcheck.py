#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
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


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def publish_mqtt(
    *,
    enabled: bool,
    host: str,
    port: int,
    topic: str,
    username: str | None,
    password: str | None,
    retain: bool,
    payload: dict,
) -> None:
    if not enabled:
        return
    if not host or not topic:
        return
    cmd = ["mosquitto_pub", "-h", host, "-p", str(port), "-t", topic, "-m", json.dumps(payload, separators=(",", ":"))]
    if username:
        cmd += ["-u", username]
    if password:
        cmd += ["-P", password]
    if retain:
        cmd += ["-r"]
    p = run(cmd)
    if p.returncode != 0:
        print(f"WARN mqtt_publish_failed rc={p.returncode} err={p.stderr.strip()!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Health-check for tigo-ingest + Influx writes")
    ap.add_argument("--service", default="tigo-ingest.service")
    ap.add_argument("--db", default="bms")
    ap.add_argument("--rp", default="autogen")
    ap.add_argument("--measurement", default="tigo_power_report")
    ap.add_argument("--max-lag-min", type=int, default=240, help="Fail if latest point is older than this")
    ap.add_argument("--mqtt-enabled", action="store_true", default=_env_bool("TIGO_HEALTH_MQTT_ENABLED", False))
    ap.add_argument("--mqtt-host", default=os.getenv("TIGO_HEALTH_MQTT_HOST", "127.0.0.1"))
    ap.add_argument("--mqtt-port", type=int, default=int(os.getenv("TIGO_HEALTH_MQTT_PORT", "1883")))
    ap.add_argument("--mqtt-topic", default=os.getenv("TIGO_HEALTH_MQTT_TOPIC", "tigo/health"))
    ap.add_argument("--mqtt-user", default=os.getenv("TIGO_HEALTH_MQTT_USER"))
    ap.add_argument("--mqtt-pass", default=os.getenv("TIGO_HEALTH_MQTT_PASS"))
    ap.add_argument("--mqtt-retain", action="store_true", default=_env_bool("TIGO_HEALTH_MQTT_RETAIN", True))
    args = ap.parse_args()

    now = datetime.now(timezone.utc)

    status = run(["systemctl", "is-active", args.service])
    if status.returncode != 0 or status.stdout.strip() != "active":
        msg = f"CRIT service_not_active service={args.service} state={status.stdout.strip()!r}"
        publish_mqtt(
            enabled=args.mqtt_enabled,
            host=args.mqtt_host,
            port=args.mqtt_port,
            topic=args.mqtt_topic,
            username=args.mqtt_user,
            password=args.mqtt_pass,
            retain=args.mqtt_retain,
            payload={
                "status": "CRIT",
                "reason": "service_not_active",
                "service": args.service,
                "state": status.stdout.strip(),
                "ts_utc": now.isoformat(),
            },
        )
        print(msg)
        return 2

    q = f'SELECT last("power_w") FROM "{args.rp}"."{args.measurement}"'
    influx = run(["influx", "-database", args.db, "-format", "json", "-execute", q])
    if influx.returncode != 0:
        msg = f"CRIT influx_query_failed rc={influx.returncode} err={influx.stderr.strip()!r}"
        publish_mqtt(
            enabled=args.mqtt_enabled,
            host=args.mqtt_host,
            port=args.mqtt_port,
            topic=args.mqtt_topic,
            username=args.mqtt_user,
            password=args.mqtt_pass,
            retain=args.mqtt_retain,
            payload={
                "status": "CRIT",
                "reason": "influx_query_failed",
                "service": args.service,
                "db": args.db,
                "ts_utc": now.isoformat(),
            },
        )
        print(msg)
        return 2

    last_ts = parse_last_point_time(influx.stdout)
    if last_ts is None:
        msg = "CRIT no_points_found"
        publish_mqtt(
            enabled=args.mqtt_enabled,
            host=args.mqtt_host,
            port=args.mqtt_port,
            topic=args.mqtt_topic,
            username=args.mqtt_user,
            password=args.mqtt_pass,
            retain=args.mqtt_retain,
            payload={
                "status": "CRIT",
                "reason": "no_points_found",
                "service": args.service,
                "db": args.db,
                "measurement": f"{args.rp}.{args.measurement}",
                "ts_utc": now.isoformat(),
            },
        )
        print(msg)
        return 2

    lag_min = (now - last_ts).total_seconds() / 60.0
    if lag_min > args.max_lag_min:
        msg = f"CRIT stale_data lag_min={lag_min:.1f} max_lag_min={args.max_lag_min} last_ts_utc={last_ts.isoformat()}"
        publish_mqtt(
            enabled=args.mqtt_enabled,
            host=args.mqtt_host,
            port=args.mqtt_port,
            topic=args.mqtt_topic,
            username=args.mqtt_user,
            password=args.mqtt_pass,
            retain=args.mqtt_retain,
            payload={
                "status": "CRIT",
                "reason": "stale_data",
                "service": args.service,
                "db": args.db,
                "measurement": f"{args.rp}.{args.measurement}",
                "lag_min": round(lag_min, 1),
                "max_lag_min": args.max_lag_min,
                "last_ts_utc": last_ts.isoformat(),
                "ts_utc": now.isoformat(),
            },
        )
        print(msg)
        return 2

    msg = f"OK lag_min={lag_min:.1f} last_ts_utc={last_ts.isoformat()}"
    publish_mqtt(
        enabled=args.mqtt_enabled,
        host=args.mqtt_host,
        port=args.mqtt_port,
        topic=args.mqtt_topic,
        username=args.mqtt_user,
        password=args.mqtt_pass,
        retain=args.mqtt_retain,
        payload={
            "status": "OK",
            "reason": "healthy",
            "service": args.service,
            "db": args.db,
            "measurement": f"{args.rp}.{args.measurement}",
            "lag_min": round(lag_min, 1),
            "max_lag_min": args.max_lag_min,
            "last_ts_utc": last_ts.isoformat(),
            "ts_utc": now.isoformat(),
        },
    )
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
