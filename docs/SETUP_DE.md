# Tigo RS485 -> InfluxDB + Grafana (tigo-ingest)

Diese Anleitung beschreibt ein Setup auf dem Raspberry Pi:

* Datenquelle: Tigo CCA/Gateway RS485 (Sniff/Monitor) via USB-RS485 Adapter
* Decoder: `taptap observe` (JSON Lines)
* Ingest: `tigo-ingest` schreibt nach InfluxDB 1.x (`bms`, RP default `autogen`)
* Visualisierung: Grafana Dashboard Import JSON

## 1) Voraussetzungen

* InfluxDB 1.x (InfluxQL) laeuft lokal: `http://127.0.0.1:8086`
* Grafana laeuft und hat eine InfluxDB (InfluxQL) Datasource auf die DB `bms`
* Python 3.11+
* USB-RS485 Adapter (empfohlen FTDI) am Pi

## 2) RS485 Verkabelung (parallel sniffen)

Du klemmst den RS485-Adapter parallel an den Gateway-RS485 Port (Bus bleibt in Betrieb):

* Adapter `A` -> Gateway `A` (manchmal `D+`)
* Adapter `B` -> Gateway `B` (manchmal `D-`)
* wenn vorhanden: `GND` verbinden (hilft oft bei stabiler Kommunikation)
* keine zusaetzliche Terminierung am Sniffer-Adapter aktivieren (nur Bus-Enden terminieren)
* Leitung kurz halten (Stub minimieren)

Wenn keine Daten kommen: A/B einmal tauschen.

## 3) `taptap` installieren

Auf Debian/Raspberry Pi ist das `cargo` aus `apt` oft zu alt fuer `taptap`.
Empfohlen: Rust via `rustup`.

```bash
sudo apt-get update
sudo apt-get install -y curl pkg-config libudev-dev

curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal
. $HOME/.cargo/env

cargo install taptap --locked
taptap --help
```

## 4) Projekt installieren

```bash
cd /home/black/tigo-ingest
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## 5) Serial Device finden

```bash
. $HOME/.cargo/env
taptap list-serial-ports
ls -la /dev/serial/by-id/
```

Empfehlung: immer den stabilen Pfad `/dev/serial/by-id/...` verwenden, nicht `/dev/ttyUSB*`.

Wenn ein Port "busy" ist:
```bash
sudo fuser -v /dev/ttyUSB0 || true
sudo fuser -v /dev/ttyUSB1 || true
sudo fuser -v /dev/ttyUSB2 || true
```

## 6) `tigo-ingest` konfigurieren

```bash
cd /home/black/tigo-ingest
cp .env.example .env
```

In `.env` setzen:

* `TAPTAP_CMD="taptap observe --serial /dev/serial/by-id/<DEIN-ADAPTER>"`
* `INFLUX_DB=bms`
* `INFLUX_RP=` (leer = DB default `autogen` = unbegrenzt)
* `INFLUX_MEASUREMENT=tigo_power_report`

## 7) Smoketest (vor systemd)

```bash
cd /home/black/tigo-ingest
sudo systemctl stop tigo-ingest.service || true
./scripts/rs485-smoketest.sh
```

Erwartung: JSON-Zeilen mit Feldern wie `voltage_in`, `current`, `timestamp`, `dc_dc_duty_cycle`, ...

## 8) Als Dienst starten

```bash
sudo cp /home/black/tigo-ingest/systemd/tigo-ingest.service /etc/systemd/system/tigo-ingest.service
sudo systemctl daemon-reload
sudo systemctl enable --now tigo-ingest.service
systemctl status --no-pager -n 20 tigo-ingest.service
```

Logs:
```bash
journalctl -u tigo-ingest.service -f
```

## 9) Influx Verifikation

```bash
influx -database bms -execute 'SHOW MEASUREMENTS' | rg tigo
influx -database bms -execute 'SELECT * FROM autogen.tigo_power_report ORDER BY time DESC LIMIT 5'
```

## 10) Grafana Dashboard importieren

Datei:

* `tigo-ingest/grafana/tigo-influxdb-autogen-dashboard.json`

Import:

1. Grafana: Dashboards -> Import
2. JSON einfuegen / Datei auswaehlen
3. Variable `DS_INFLUX` auf deine InfluxDB Datasource mappen

Dashboard Variablen:

* `gateway_id` (All oder spezifisch)
* `node_id` (All oder Filter auf einzelne Optimierer)

## Influx Schema (Measurement `tigo_power_report`)

Tags:
* `src=tigo`
* `gateway_id`
* `node_id`
* optional: `gateway_addr`, `node_addr`, `barcode`

Fields:
* `voltage_in_v`, `voltage_out_v`
* `current_in_a`
* `power_w`
* `current_out_a` (berechnet)
* `duty_cycle`
* `temperature_c`
* `rssi`

