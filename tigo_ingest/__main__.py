from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import sys
import time

from dotenv import load_dotenv

from .influx import InfluxConfig, InfluxWriter, line_protocol
from .taptap_reader import parse_power_report, parse_taptap_event


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _run(taptap_cmd: list[str]) -> int:
    log = logging.getLogger("tigo_ingest")

    proc = await asyncio.create_subprocess_exec(
        *taptap_cmd,
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

    influx_cfg = InfluxConfig.from_env()
    influx = InfluxWriter(influx_cfg)

    batch: list[str] = []
    batch_max = int(os.getenv("INFLUX_BATCH_MAX", "250"))
    batch_flush_s = float(os.getenv("INFLUX_BATCH_FLUSH_S", "2.0"))
    last_flush = time.monotonic()

    async def _flush_if_needed(force: bool = False) -> None:
        nonlocal last_flush, batch
        now = time.monotonic()
        if not force and len(batch) < batch_max and (now - last_flush) < batch_flush_s:
            return
        if not batch:
            last_flush = now
            return
        lines = batch
        batch = []
        last_flush = now
        await asyncio.to_thread(influx.write_lines, lines)

    try:
        while True:
            b = await proc.stdout.readline()
            if not b:
                break

            line = b.decode(errors="replace").strip()
            if not line:
                continue

            try:
                event_type, payload = parse_taptap_event(line)
            except Exception:
                log.exception("Failed to parse event line: %r", line[:4000])
                continue

            if event_type != "power_report":
                continue

            try:
                pr = parse_power_report(payload)
            except Exception:
                log.exception("Failed to parse power_report payload: %s", json.dumps(payload)[:4000])
                continue

            power_w = pr.voltage_in * pr.current
            current_out = None
            if pr.voltage_out not in (0.0, -0.0):
                current_out = power_w / pr.voltage_out

            tags = {
                "src": "tigo",
                "gateway_id": str(pr.gateway_id),
                "node_id": str(pr.node_id),
            }
            if pr.gateway_address is not None:
                tags["gateway_addr"] = str(pr.gateway_address)
            if pr.node_address is not None:
                tags["node_addr"] = str(pr.node_address)
            if pr.node_barcode:
                tags["barcode"] = pr.node_barcode

            fields = {
                "voltage_in_v": pr.voltage_in,
                "voltage_out_v": pr.voltage_out,
                "current_in_a": pr.current,
                "power_w": power_w,
                "current_out_a": current_out,
                "duty_cycle": pr.duty_cycle,
                "temperature_c": pr.temperature,
                "rssi": pr.rssi,
            }

            batch.append(
                line_protocol(
                    measurement=influx_cfg.measurement,
                    tags=tags,
                    fields=fields,
                    timestamp=pr.timestamp,  # use measurement time from payload
                )
            )
            await _flush_if_needed()

        await _flush_if_needed(force=True)
    finally:
        stderr_task.cancel()
        try:
            await stderr_task
        except Exception:
            pass
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

    return proc.returncode or 0


def main() -> int:
    # Avoid python-dotenv's find_dotenv() heuristics (can assert in some contexts).
    load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"))

    _setup_logging(os.getenv("LOG_LEVEL", "INFO"))

    taptap_cmd_s = os.getenv("TAPTAP_CMD", "").strip()
    if not taptap_cmd_s:
        print(
            "Missing TAPTAP_CMD. Example: TAPTAP_CMD='taptap observe --tcp 192.168.2.30 --port 7160'",
            file=sys.stderr,
        )
        return 2

    taptap_cmd = shlex.split(taptap_cmd_s)

    return asyncio.run(_run(taptap_cmd))


if __name__ == "__main__":
    raise SystemExit(main())
