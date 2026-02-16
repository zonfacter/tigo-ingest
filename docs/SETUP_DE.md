# Tigo RS485 -> InfluxDB + Grafana (tigo-ingest)

Diese Anleitung beschreibt ein Setup (z.B. Raspberry Pi), um Tigo Optimierer-Daten aus einem RS485-Bus auszulesen und in InfluxDB zu speichern.

Kurz: `taptap observe` (RS485 sniff) -> `tigo-ingest` -> InfluxDB 1.x -> Grafana.

## 1) Voraussetzungen

* Linux Host mit `systemd` (empfohlen) und Python 3.11+
* USB-RS485 Adapter (empfohlen FTDI; funktioniert auch CH34x)
* InfluxDB 1.x (InfluxQL) erreichbar, z.B. `http://127.0.0.1:8086`
* Grafana mit InfluxDB (InfluxQL / InfluxDB 1.x) Datasource auf DB `bms`

Pakete (Debian/RPi OS):
```bash
sudo apt-get update
sudo apt-get install -y curl git pkg-config libudev-dev
```

## 2) Architektur (Kurz)

```text
Tigo Gateway/CCA RS485 Bus  -->  USB-RS485 Adapter  -->  taptap observe (JSONL)
                                                      -->  tigo-ingest (Influx line protocol)
                                                      -->  InfluxDB 1.x (DB=bms, RP=autogen)
                                                      -->  Grafana Dashboard
```

Hinweis: In diesem Setup ist RS485/USB der Weg. Das Gateway bietet i.d.R. nur HTTP an, aber keinen Serial-over-TCP Dienst.

## 3) RS485 Verkabelung (parallel sniffen)

Du klemmst den RS485-Adapter parallel an den Gateway-RS485 Port (Bus bleibt in Betrieb):

* Adapter `A` -> Gateway `A` (manchmal `D+`)
* Adapter `B` -> Gateway `B` (manchmal `D-`)
* wenn vorhanden: `GND` verbinden (hilft oft bei stabiler Kommunikation)
* keine zusaetzliche Terminierung am Sniffer-Adapter aktivieren (nur Bus-Enden terminieren)
* Leitung kurz halten (Stub minimieren)

Wenn keine Daten kommen: A/B einmal tauschen.

## 4) Benutzerrechte (Serial Zugriff)

Der User, der `tigo-ingest` ausfuehrt, braucht Zugriff auf serielle Devices. Auf Debian ist das i.d.R. Gruppe `dialout`.

```bash
id
groups
sudo usermod -aG dialout "$USER"
# Danach einmal neu einloggen.
```

## 5) `taptap` installieren (Decoder/CLI)

Auf Debian/RPi OS ist `cargo` aus `apt` oft zu alt fuer `taptap`. Empfohlen ist Rust via `rustup`:

```bash
curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal
. "$HOME/.cargo/env"

cargo install taptap --locked
taptap --help
```

## 6) Repo holen und Python Umgebung

```bash
cd ~
git clone https://github.com/zonfacter/tigo-ingest.git
cd tigo-ingest

python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## 7) RS485 Adapter/Port finden (stabiler Pfad)

Serial Ports anzeigen:
```bash
. "$HOME/.cargo/env"
taptap list-serial-ports
ls -la /dev/serial/by-id/
```

Empfehlung: immer `/dev/serial/by-id/...` verwenden, nicht `/dev/ttyUSB*` (USB-Hubs aendern sonst gern die Nummern).

Wenn ein Port "busy" ist:
```bash
sudo fuser -v /dev/ttyUSB0 || true
sudo fuser -v /dev/ttyUSB1 || true
sudo fuser -v /dev/ttyUSB2 || true
```

## 8) InfluxDB vorbereiten (einmalig)

Wenn du die DB schon hast (z.B. aus anderen Projekten), kannst du das ueberspringen.

```bash
influx -execute 'CREATE DATABASE bms'
influx -database bms -execute 'SHOW RETENTION POLICIES ON bms'
```

`tigo-ingest` schreibt standardmaessig in die Default-Retention `autogen` (unbegrenzt), solange `INFLUX_RP` leer ist.

## 9) `tigo-ingest` konfigurieren (.env)

```bash
cd ~/tigo-ingest
cp .env.example .env
```

In `~/tigo-ingest/.env` anpassen:

* `TAPTAP_CMD="taptap observe --serial /dev/serial/by-id/<DEIN-ADAPTER>"`
  * Tipp: Wenn `taptap` via rustup installiert ist, kann ein voller Pfad robuster sein:
    * `TAPTAP_CMD="/home/<user>/.cargo/bin/taptap observe --serial ..."`
* `INFLUX_URL=http://127.0.0.1:8086`
* `INFLUX_DB=bms`
* `INFLUX_RP=` (leer = Default `autogen` = unbegrenzt)
* `INFLUX_MEASUREMENT=tigo_power_report`

## 10) Smoketest (vor systemd)

Der Smoketest zeigt sofort, ob ueber RS485 JSON-Events reinkommen.

```bash
cd ~/tigo-ingest
sudo systemctl stop tigo-ingest.service || true
./scripts/rs485-smoketest.sh
```

Erwartung: JSON-Zeilen mit Feldern wie `timestamp`, `voltage_in`, `voltage_out`, `current`, `dc_dc_duty_cycle`, `temperature`, `rssi`.

## 11) systemd Service installieren

Im Repo liegt eine Beispiel-Unit: `systemd/tigo-ingest.service`.
Wenn dein Install-Pfad oder User anders ist, passe darin diese Zeilen an:

* `User=...`
* `WorkingDirectory=...`
* `EnvironmentFile=...`
* `ExecStart=...`

Install + Start:
```bash
cd ~/tigo-ingest
sudo cp ./systemd/tigo-ingest.service /etc/systemd/system/tigo-ingest.service
sudo systemctl daemon-reload
sudo systemctl enable --now tigo-ingest.service
systemctl status --no-pager -n 20 tigo-ingest.service
```

Logs:
```bash
journalctl -u tigo-ingest.service -f
```

## 11b) Optional: automatischer Health-Check (Timer)

Damit ein Ausfall wie am 16.02.2026 schnell auffaellt, gibt es einen periodischen Check:

* Script: `scripts/tigo_healthcheck.py`
* Unit: `systemd/tigo-ingest-healthcheck.service`
* Timer: `systemd/tigo-ingest-healthcheck.timer` (alle 10 Minuten)

Installation:
```bash
cd ~/tigo-ingest
sudo cp ./systemd/tigo-ingest-healthcheck.service /etc/systemd/system/tigo-ingest-healthcheck.service
sudo cp ./systemd/tigo-ingest-healthcheck.timer /etc/systemd/system/tigo-ingest-healthcheck.timer
sudo systemctl daemon-reload
sudo systemctl enable --now tigo-ingest-healthcheck.timer
systemctl status --no-pager -n 20 tigo-ingest-healthcheck.timer
```

Manuell testen:
```bash
cd ~/tigo-ingest
./scripts/tigo_healthcheck.py --service tigo-ingest.service --db bms --rp autogen --measurement tigo_power_report --max-lag-min 240
```

Optional MQTT Statusmeldungen aktivieren (`OK`/`CRIT`):
```bash
cd ~/tigo-ingest
cp -n .env.example .env
sed -i 's/^TIGO_HEALTH_MQTT_ENABLED=.*/TIGO_HEALTH_MQTT_ENABLED=1/' .env
# optional: Host/Port/Topic/User/Pass in .env anpassen
sudo systemctl daemon-reload
sudo systemctl restart tigo-ingest-healthcheck.timer
```

Soforttest mit MQTT:
```bash
cd ~/tigo-ingest
TIGO_HEALTH_MQTT_ENABLED=1 ./scripts/tigo_healthcheck.py --service tigo-ingest.service --db bms --rp autogen --measurement tigo_power_report --max-lag-min 240
```

Log-Ausgabe:
* `OK ...` = Dienst aktiv und letzte Punkte nicht zu alt
* `CRIT stale_data ...` = Dienst aktiv, aber keine frischen Daten
* `CRIT service_not_active ...` = Dienst nicht aktiv

MQTT Payload (JSON) enthaelt u.a.:
* `status` (`OK`/`CRIT`)
* `reason` (z.B. `healthy`, `stale_data`)
* `lag_min`, `last_ts_utc`, `ts_utc`

## 12) Influx Verifikation

```bash
influx -database bms -execute 'SHOW MEASUREMENTS' | rg tigo
influx -database bms -execute 'SELECT * FROM autogen.tigo_power_report ORDER BY time DESC LIMIT 5'
```

## 13) Grafana Dashboard importieren

Grafana Datasource (InfluxQL / InfluxDB 1.x) muss auf DB `bms` zeigen:

* URL: `http://<influx-host>:8086`
* Database: `bms`

Dashboard JSON:

* `grafana/tigo-influxdb-autogen-dashboard.json`

Import:

1. Grafana: Dashboards -> Import
2. JSON einfuegen / Datei auswaehlen
3. Variable `DS_INFLUX` auf deine InfluxDB Datasource mappen

Dashboard Variablen:

* `gateway_id` (All oder spezifisch)
* `node_id` (All oder Filter auf einzelne Optimierer)

Hinweis zur Gesamtleistung:

* Die Optimierer melden nicht alle gleichzeitig. Wenn man einfach alle `power_w` Werte in kleinen Zeitfenstern aufsummiert, wird es je nach Intervall zu hoch/zu niedrig.
* Das Dashboard nutzt daher fuer die Gesamtleistung eine 1-Minuten Aggregation: pro Optimierer `mean(power_w)` je Minute, danach Summe ueber alle Optimierer.
* Zusaetzlich gibt es ein Debug-Panel **\"Tigo Total Power RAW SUM (debug)\"** das die naive Variante `sum(power_w)` zeigt, um Abweichungen schnell zu erkennen.
* Es gibt ein Panel **\"Reports Per Node (count/min)\"**, das pro `node_id` zeigt, wie viele Reports pro Minute ankommen. Nodes mit deutlich weniger Reports sind oft die Ursache fuer Abweichungen/\"fehlende\" Leistung.

## 14) Betrieb / Updates

Update aus GitHub:
```bash
cd ~/tigo-ingest
git pull
sudo systemctl restart tigo-ingest.service
```

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

## Troubleshooting

### Smoketest liefert keine JSON-Zeilen

* A/B vertauscht: einmal tauschen.
* Falscher RS485-Port am Gateway: am richtigen Port parallel anschliessen.
* Falsches Device: by-id Pfad verwenden (`/dev/serial/by-id/...`).
* USB-Hub: `ttyUSB*` Nummern koennen sich aendern.

### `Device or resource busy`

```bash
sudo fuser -v /dev/ttyUSB0 || true
sudo fuser -v /dev/ttyUSB1 || true
sudo fuser -v /dev/ttyUSB2 || true
```

### Service laeuft, aber nichts in Influx

Logs:
```bash
journalctl -u tigo-ingest.service -n 200 --no-pager
```

Influx erreichbar:
```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8086/ping
```

### Schlechte Nodes (RSSI / unregelmaessige Reports) finden

Praktisch ist nicht nur der RSSI-Wert selbst, sondern vor allem, welche `node_id` **deutlich weniger Reports** liefert als der Rest.

Script (fragt InfluxDB ab und listet auffaellige Nodes):
```bash
cd ~/tigo-ingest
./scripts/rssi_report.py --hours 24 --top 15
```

Es zeigt:
* niedrigste Report-Counts (haeufig die Ursache fuer \"fehlende\" Leistung)
* hoechste/niedrigste RSSI-Mittelwerte zum Vergleich

## Quellen / Credits

Siehe `docs/SOURCES.md`.
