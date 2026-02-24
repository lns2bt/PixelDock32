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
# optionaler GPIO-Backend-Fallback (v. a. bei Python 3.13):
# lgpio aus pip braucht Build-Tools UND die native lgpio-Library
sudo apt update && sudo apt install -y swig python3-dev liblgpio-dev
pip install lgpio
# Alternative ohne pip-Build (Systempaket):
# sudo apt install -y python3-lgpio
cp .env.example .env
```

Optional: Admin-Passwort in `.env` anpassen.

## Start

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Dann im LAN öffnen: `http://<raspberrypi-ip>:8000`


## Arduino Nano als LED-Co-Prozessor (empfohlen)

1. Arduino IDE öffnen und `arduino/PixelDockNano/PixelDockNano.ino` flashen.
2. Bibliothek installieren: `Adafruit NeoPixel`.
3. Verdrahtung:
   - Nano `D6` -> `DIN` erstes WS2812B-Panel
   - Nano `GND` -> Panel `GND` und Raspberry Pi `GND`
   - Externe 5V-Versorgung für LED-Panels verwenden (nicht über USB speisen).
4. Nano per USB an den Raspberry Pi anschließen.
5. In `.env` setzen:

```env
LED_TRANSPORT=serial
LED_SERIAL_PORT=/dev/ttyUSB0
LED_SERIAL_BAUDRATE=1000000
```

Tipp: Mit `LED_TRANSPORT=auto` nutzt die App automatisch Serial, wenn `rpi_ws281x` nicht verfügbar ist.

Debug bei Verbindungsproblemen: In der Debug-UI stehen jetzt `LED/Serial Debug` und `Serial Ping (Pi ↔ Nano)` bereit. Damit siehst du Transportstatus, Frame-Zähler, letzte Fehler und Roundtrip-Zeit direkt im Webinterface.

## systemd Autostart

Für den produktiven Betrieb auf dem Raspberry Pi gibt es jetzt eine vollständige Schritt-für-Schritt-Anleitung inkl. Healthcheck-Recovery bei Hängern:

- [`docs/autostart-raspberry-pi.md`](autostart-raspberry-pi.md)

Kurzvariante:

```bash
cd /home/pi/PixelDock32
sudo ./scripts/manage-autostart.sh enable --repo-dir /home/pi/PixelDock32 --user pi --group pi
```

## Wichtige .env Parameter

- LED Treiber: `LED_*` (wichtig: `LED_TRANSPORT`, `LED_SERIAL_*`)
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
# optionaler GPIO-Backend-Fallback (v. a. bei Python 3.13):
# lgpio aus pip braucht Build-Tools UND die native lgpio-Library
sudo apt update && sudo apt install -y swig python3-dev liblgpio-dev
pip install lgpio
# Alternative ohne pip-Build (Systempaket):
# sudo apt install -y python3-lgpio
```

Danach `uvicorn app.main:app --host 0.0.0.0 --port 8000` erneut starten.


Weitere häufige GPIO/DHT-Fehler:

- `RPi.GPIO library not available in this environment`
- `DHT polling failed: Unknown platform.`
- `cannot find -llgpio: No such file or directory`

Ursache: App läuft nicht direkt auf dem Raspberry Pi (oder ohne GPIO-Rechte), bzw. die GPIO-/DHT-Bibliotheken fehlen in genau dieser Runtime (venv, Service-User, Container).

Empfohlene Debug-Methode (Web-UI):

1. **GPIO-Umgebung prüfen** im Bereich „GPIO Pin Finder“ ausführen.
2. In der Ausgabe kontrollieren:
   - `backend` (ist `RPi.GPIO` verfügbar?)
   - `can_setup_input` und `input_error`
   - `/dev/gpiomem` Existenz/Berechtigung
   - erkannte DHT/GPIO-Libraries unter `libraries`
3. Danach erst **Output-Test** (LED-Datenpin) und **Input-Probe** (Sensor-Pin) starten.
4. Im Bereich **Debug & Tools** zusätzlich **DHT Read Once** ausführen und prüfen, ob Temperatur/Feuchte oder ein klarer Backend-Fehler angezeigt wird.

Typische Fixes auf dem Pi:

```bash
# Beispielpakete je nach Distribution
sudo apt update
sudo apt install -y python3-rpi-gpio || sudo apt install -y python3-rpi-lgpio

source .venv/bin/activate
pip install adafruit-circuitpython-dht adafruit-blinka
# wenn RPi.GPIO im venv nicht importierbar ist (häufig auf Python 3.13):
# lgpio aus pip braucht Build-Tools UND die native lgpio-Library
sudo apt install -y swig python3-dev liblgpio-dev
pip install lgpio
# Alternative ohne pip-Build (Systempaket):
# sudo apt install -y python3-lgpio
```

Anschließend App/Service neu starten.
