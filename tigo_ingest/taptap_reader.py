from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime


log = logging.getLogger(__name__)


def _parse_dt(s: str) -> datetime:
    # taptap uses RFC3339; Python's fromisoformat handles offsets and also "Z" with minor fix.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


@dataclass(frozen=True)
class PowerReport:
    timestamp: datetime
    gateway_id: int
    gateway_address: str | None
    node_id: int
    node_address: str | None
    node_barcode: str | None
    voltage_in: float
    voltage_out: float
    current: float
    duty_cycle: float
    temperature: float
    rssi: int


def parse_taptap_event(line: str) -> tuple[str, dict]:
    obj = json.loads(line)
    if not isinstance(obj, dict):
        raise ValueError("Unexpected event (expected object)")

    # Format A (envelope): {"power_report": {...}}
    if len(obj) == 1:
        event_type = next(iter(obj.keys()))
        payload = obj[event_type]
        if isinstance(payload, dict):
            return event_type, payload

    # Format B (bare power_report payload): {"gateway":{...},"node":{...},"timestamp":...,"voltage_in":...}
    if "gateway" in obj and "node" in obj and "timestamp" in obj and "voltage_in" in obj and "current" in obj:
        return "power_report", obj

    raise ValueError("Unexpected event envelope (expected single-key object or bare power_report)")


def parse_power_report(payload: dict) -> PowerReport:
    # Matches taptap's Event::PowerReport schema:
    # { timestamp, gateway: {id,address}, node: {id,address,barcode?}, ... }
    ts = _parse_dt(payload["timestamp"])
    gw = payload["gateway"]
    node = payload["node"]

    duty = payload.get("duty_cycle")
    if duty is None:
        duty = payload.get("dc_dc_duty_cycle")
    if duty is None:
        raise KeyError("missing duty_cycle/dc_dc_duty_cycle")

    return PowerReport(
        timestamp=ts,
        gateway_id=int(gw["id"]),
        gateway_address=_normalize_address(gw.get("address")),
        node_id=int(node["id"]),
        node_address=_normalize_address(node.get("address")),
        node_barcode=node.get("barcode"),
        voltage_in=float(payload["voltage_in"]),
        voltage_out=float(payload["voltage_out"]),
        current=float(payload["current"]),
        duty_cycle=float(duty),
        temperature=float(payload["temperature"]),
        rssi=int(payload["rssi"]),
    )


async def run_taptap_cmd(cmd: list[str]):
    # Yields stdout lines from the subprocess.
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None

    async def _stderr_logger():
        while True:
            b = await proc.stderr.readline()
            if not b:
                return
            log.warning("taptap stderr: %s", b.decode(errors="replace").rstrip())

    stderr_task = asyncio.create_task(_stderr_logger())
    try:
        while True:
            b = await proc.stdout.readline()
            if not b:
                break
            yield b.decode(errors="replace").rstrip("\n")
    finally:
        stderr_task.cancel()
        with contextlib.suppress(Exception):
            await stderr_task
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
    def _normalize_address(v) -> str | None:
        if v is None:
            return None
        if isinstance(v, int):
            return str(v)
        # Newer taptap payloads may emit address as byte array, e.g. [4,192,...]
        if isinstance(v, list):
            try:
                parts = [int(x) & 0xFF for x in v]
                return "".join(f"{x:02x}" for x in parts)
            except Exception:
                return str(v)
        return str(v)
