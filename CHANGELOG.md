# Changelog

## Unreleased

## v1.1.1

* Fix: `NameError` bei `_normalize_address` beseitigt (Tigo-Payload Parsing schreibt wieder stabil in Influx)
* Fix: `gateway.address` / `node.address` auch als Byte-Array robust normalisiert
* Neu: Health-Check kann Status als MQTT JSON (`OK`/`CRIT`) publizieren (`TIGO_HEALTH_MQTT_*`)
* Service: `tigo-ingest-healthcheck.service` liest optional `.env` via `EnvironmentFile`
* Doku/CLI: Exit-Codes fuer Healthcheck klar dokumentiert (`0=OK`, `2=CRIT`, `1=Runtime/Usage`)

## v1.1.0

* Fix: Parser akzeptiert `gateway.address` / `node.address` auch als Byte-Array (kompatibel zu geaenderten `taptap` Payloads)
* Neu: automatischer Health-Check (`scripts/tigo_healthcheck.py`) fuer Dienststatus + Stale-Data Erkennung
* Neu: `systemd` Health-Check Unit + Timer (`tigo-ingest-healthcheck.service` / `.timer`)
* Doku: Setup/README um Health-Check erweitert

## v1.0.0

* RS485 ingest via `taptap observe` (JSON lines) -> InfluxDB 1.x (InfluxQL)
* Measurement `tigo_power_report` mit Tags/Fields fuer Optimierer Power Reports
* systemd Service (`systemd/tigo-ingest.service`) + Runner/Prechecks (`run.sh`)
* Grafana Dashboard Import JSON inkl. Debug-Panel fuer RAW SUM
* Setup-Dokumentation (DE) und Quellen/Credits
