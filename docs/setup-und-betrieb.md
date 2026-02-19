# Setup und Betrieb

## Setup

```bash
cd /path/to/PixelDock32
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# nur auf Raspberry Pi mit DHT-Sensor erforderlich:
pip install Adafruit_DHT==1.4.0 --config-settings="--build-option=--force-pi"
# Alternative (falls Adafruit_DHT/Plattform-Erkennung fehlschlägt):
pip install adafruit-circuitpython-dht adafruit-blinka
cp .env.example .env
```

Optional: Admin-Passwort in `.env` anpassen.

## Start

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Dann im LAN öffnen: `http://<raspberrypi-ip>:8000`

## systemd Autostart

Service-Datei: `systemd/pixeldock32.service`

Installation am Pi:

```bash
sudo cp systemd/pixeldock32.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable pixeldock32
sudo systemctl start pixeldock32
sudo systemctl status pixeldock32
```

## Wichtige .env Parameter

- LED Treiber: `LED_*`
- Mapping: `DATA_STARTS_RIGHT`, `SERPENTINE`, `FIRST_PIXEL_OFFSET`
- Render/Polling: `RENDER_FPS`, `POLL_BTC_SECONDS`, `POLL_WEATHER_SECONDS`
- Wetter/BTC APIs: `WEATHER_*`, `BTC_API_URL`

## Troubleshooting

Wenn beim Start folgender Fehler kommt:

- `ValueError: the greenlet library is required to use this function. No module named "greenlet"`

Dann wurden die Python-Abhängigkeiten unvollständig installiert. Neu installieren:

```bash
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# optional, falls DHT verwendet wird:
pip install Adafruit_DHT==1.4.0 --config-settings="--build-option=--force-pi"
# Alternative (falls Adafruit_DHT/Plattform-Erkennung fehlschlägt):
pip install adafruit-circuitpython-dht adafruit-blinka
```

Danach `uvicorn app.main:app --host 0.0.0.0 --port 8000` erneut starten.


Weitere häufige GPIO/DHT-Fehler:

- `RPi.GPIO library not available in this environment`
- `DHT polling failed: Unknown platform.`

Ursache: App läuft nicht direkt auf dem Raspberry Pi (oder ohne GPIO-Rechte), bzw. die GPIO-/DHT-Bibliotheken fehlen in genau dieser Runtime (venv, Service-User, Container).

Empfohlene Debug-Methode (Web-UI):

1. **GPIO-Umgebung prüfen** im Bereich „GPIO Pin Finder“ ausführen.
2. In der Ausgabe kontrollieren:
   - `backend` (ist `RPi.GPIO` verfügbar?)
   - `can_setup_input` und `input_error`
   - `/dev/gpiomem` Existenz/Berechtigung
   - erkannte DHT/GPIO-Libraries unter `libraries`
3. Danach erst **Output-Test** (LED-Datenpin) und **Input-Probe** (Sensor-Pin) starten.

Typische Fixes auf dem Pi:

```bash
# Beispielpakete je nach Distribution
sudo apt update
sudo apt install -y python3-rpi-gpio || sudo apt install -y python3-rpi-lgpio

source .venv/bin/activate
pip install adafruit-circuitpython-dht adafruit-blinka
```

Anschließend App/Service neu starten.
