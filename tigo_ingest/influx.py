from __future__ import annotations

import base64
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone


log = logging.getLogger(__name__)


def _dt_to_ns(dt: datetime) -> int:
    if dt.tzinfo is None:
        # Assume UTC if naive.
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


def _escape_tag(s: str) -> str:
    # Tag keys/values: escape commas, spaces, equals.
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(" ", "\\ ").replace("=", "\\=")


def _escape_measurement(s: str) -> str:
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(" ", "\\ ")


def _escape_field_string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _format_field_value(v) -> str:
    if v is None:
        raise ValueError("Field value cannot be None")
    if isinstance(v, bool):
        return "t" if v else "f"
    if isinstance(v, int):
        return f"{v}i"
    if isinstance(v, float):
        # Influx accepts standard float repr; avoid scientific if possible is not required.
        return repr(v)
    return _escape_field_string(str(v))


def line_protocol(
    measurement: str,
    tags: dict[str, str] | None,
    fields: dict[str, object],
    timestamp: datetime,
) -> str:
    if not fields:
        raise ValueError("Need at least one field")
    m = _escape_measurement(measurement)
    tag_part = ""
    if tags:
        # Stable sort for better diffs and compression.
        items = sorted((k, v) for k, v in tags.items() if v is not None and v != "")
        if items:
            tag_part = "," + ",".join(f"{_escape_tag(str(k))}={_escape_tag(str(v))}" for k, v in items)
    field_items = sorted(fields.items())
    field_part = ",".join(f"{k}={_format_field_value(v)}" for k, v in field_items if v is not None)
    ts_ns = _dt_to_ns(timestamp)
    return f"{m}{tag_part} {field_part} {ts_ns}"


@dataclass(frozen=True)
class InfluxConfig:
    url: str
    db: str
    rp: str | None
    measurement: str
    username: str | None
    password: str | None
    dry_run: bool

    @staticmethod
    def from_env() -> "InfluxConfig":
        url = os.getenv("INFLUX_URL", "http://127.0.0.1:8086").rstrip("/")
        db = os.getenv("INFLUX_DB", "bms")
        # Default to the DB default retention policy (in InfluxDB 1.x typically `autogen` = infinite).
        rp = os.getenv("INFLUX_RP", "") or None
        measurement = os.getenv("INFLUX_MEASUREMENT", "tigo_power_report")
        username = os.getenv("INFLUX_USER") or None
        password = os.getenv("INFLUX_PASS") or None
        dry_run = os.getenv("INFLUX_DRY_RUN", "0").strip() in ("1", "true", "yes", "on")
        return InfluxConfig(
            url=url,
            db=db,
            rp=rp,
            measurement=measurement,
            username=username,
            password=password,
            dry_run=dry_run,
        )


class InfluxWriter:
    def __init__(self, cfg: InfluxConfig) -> None:
        self._cfg = cfg

    def write_lines(self, lines: list[str]) -> None:
        if not lines:
            return
        if self._cfg.dry_run:
            for ln in lines[:5]:
                log.info("INFLUX_DRY_RUN: %s", ln)
            if len(lines) > 5:
                log.info("INFLUX_DRY_RUN: ... (%d more)", len(lines) - 5)
            return

        qs = {"db": self._cfg.db, "precision": "ns"}
        if self._cfg.rp:
            qs["rp"] = self._cfg.rp
        endpoint = f"{self._cfg.url}/write?{urllib.parse.urlencode(qs)}"
        data = ("\n".join(lines) + "\n").encode("utf-8")

        req = urllib.request.Request(endpoint, data=data, method="POST")
        req.add_header("Content-Type", "text/plain; charset=utf-8")

        if self._cfg.username and self._cfg.password:
            token = base64.b64encode(f"{self._cfg.username}:{self._cfg.password}".encode("utf-8")).decode("ascii")
            req.add_header("Authorization", f"Basic {token}")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                # InfluxDB 1.x returns 204 No Content on success.
                if resp.status not in (204, 200):
                    body = resp.read(4000).decode("utf-8", errors="replace")
                    raise RuntimeError(f"Influx write failed: HTTP {resp.status}: {body}")
        except urllib.error.HTTPError as e:
            body = e.read(4000).decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            raise RuntimeError(f"Influx write failed: HTTP {getattr(e, 'code', '?')}: {body}") from e
        except Exception:
            log.exception("Influx write error (endpoint=%s, points=%d)", endpoint, len(lines))
            raise
