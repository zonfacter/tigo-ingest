# tigo-ingest

DE: Tigo Optimizer Monitoring ueber RS485: `taptap observe` -> InfluxDB 1.x -> Grafana.

EN: Tigo optimizer monitoring via RS485: `taptap observe` -> InfluxDB 1.x -> Grafana.

![Grafana Dashboard Screenshot](docs/images/grafana.jpg)

**Doku**
* Setup (ausfuehrlich, RS485, systemd, Influx, Grafana): `tigo-ingest/docs/SETUP_DE.md`
* Quellen / Credits: `tigo-ingest/docs/SOURCES.md`

**Versionierung**
* Releases/Tags ab `v1.0.0` (siehe GitHub Releases)

## Voraussetzungen

* Python 3.11+
* Ein funktionierendes `taptap` Binary (wird hier als externe Datenquelle genutzt)
* Zugriff auf die CCA/TAP Verbindung (RS485):
  * empfohlen: `--serial /dev/serial/by-id/...` (stabiler als `/dev/ttyUSB*`)
  * alternativ: `--tcp <ip>` fuer Serial-over-TCP Bridge (Port default 7160)

## Was wird geschrieben

InfluxDB Measurement (default): `tigo_power_report`

* Tags: `src=tigo`, `gateway_id`, `node_id` (optional: `gateway_addr`, `node_addr`, `barcode`)
* Fields: `voltage_in_v`, `voltage_out_v`, `current_in_a`, `power_w`, `current_out_a`, `duty_cycle`, `temperature_c`, `rssi`

## Quickstart (InfluxDB 1.x)

```bash
cd /home/black/tigo-ingest
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# .env anpassen

python -m tigo_ingest
```

Defaults schreiben unbegrenzt in die DB-Default-Retention (`autogen`) in `bms` auf `http://127.0.0.1:8086` (deine DB hat `autogen` = infinite und `rp48h` = 48h).

## systemd (optional)

```bash
sudo cp /home/black/tigo-ingest/systemd/tigo-ingest.service /etc/systemd/system/tigo-ingest.service
sudo systemctl daemon-reload
sudo systemctl enable --now tigo-ingest.service
sudo systemctl status tigo-ingest.service
```

## RS485 Vorbereitung (empfohlen)

Serial Ports anzeigen:
```bash
. $HOME/.cargo/env
taptap list-serial-ports
```

Wenn ein Port "busy" ist:
```bash
sudo fuser -v /dev/ttyUSB0 || true
sudo fuser -v /dev/ttyUSB1 || true
```

Smoketest (zeigt, ob `taptap observe` ueber RS485 Events liefert):
```bash
sudo systemctl stop tigo-ingest.service
./scripts/rs485-smoketest.sh
sudo systemctl start tigo-ingest.service
```

## Grafana Import

Dashboard JSON:
* `tigo-ingest/grafana/tigo-influxdb-autogen-dashboard.json`

Beim Import die Datasource-Variable `DS_INFLUX` auf deine InfluxDB (InfluxQL / InfluxDB 1.x, DB `bms`) mappen.

## Konfiguration

Alles laeuft ueber Umgebungsvariablen (oder `.env`):

* `TAPTAP_CMD`:
  * z.B. `taptap observe --serial /dev/serial/by-id/usb-FTDI_...`
  * oder `taptap observe --tcp <bridge-ip>` (Port default 7160)
* `INFLUX_URL`:
  * z.B. `http://127.0.0.1:8086`
* `INFLUX_DB`:
  * z.B. `bms`
* `INFLUX_RP`:
  * leer lassen = DB Default (`autogen`, infinite)
  * oder z.B. `rp48h` wenn du explizit 48h Historie willst
* `INFLUX_MEASUREMENT`:
  * default `tigo_power_report`
* `INFLUX_DRY_RUN`:
  * `1` = nicht schreiben, nur loggen
* `LOG_LEVEL`:
  * `INFO` (default), `DEBUG`

## Hinweise

* Dieses Projekt implementiert nicht das Tigo-Protokoll selbst; es nutzt `taptap` als Datenquelle.
* Wenn du InfluxDB 2.x hast (Bucket/Token), sag kurz Bescheid, dann stelle ich das auf v2 um.
