# Quellen / Credits

Dieses Projekt implementiert nicht das Tigo-Protokoll selbst, sondern nutzt bestehende Komponenten und Dokumentation.

## Externe Komponenten

* `taptap` (Will Glynn): TAP/Tigo-Protokoll Decoder und CLI, wird von `tigo-ingest` als Datenquelle genutzt.
  * Repo: https://github.com/willglynn/taptap
  * crates.io: https://crates.io/crates/taptap

## Interne Referenzen (aus diesem Workspace)

* Grafana JSON und InfluxQL-Panels/Patterns wurden an das vorhandene Setup in `bms-rs485-service-suite` angelehnt:
  * `bms-rs485-service-suite/grafana/bms-influxdb-rp48h-dashboard.json`
  * `bms-rs485-service-suite/docs/INFLUXDB_GRAFANA.md`

