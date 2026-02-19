# PixelDock32

PixelDock32 ist ein modularer 8x32-Controller für 4x WS2812B-8x8 Panels auf Raspberry Pi (GPIO18 + `rpi_ws281x`).

Das README ist bewusst kurz gehalten. Die ausführliche, aufgeteilte Projektdokumentation liegt unter [`/docs`](docs).

## Schnellstart

```bash
cd /path/to/PixelDock32
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# nur auf Raspberry Pi mit DHT-Sensor erforderlich:
pip install Adafruit_DHT==1.4.0 --config-settings="--build-option=--force-pi"
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Im LAN öffnen: `http://<raspberrypi-ip>:8000`

## Dokumentation

- [Projektüberblick & Architektur](docs/overview.md)
- [Setup, Betrieb, .env und Troubleshooting](docs/setup-und-betrieb.md)
- [API-Übersicht](docs/api.md)
- [Hardware, Mapping, Kalibrierung & DHT11](docs/hardware-und-mapping.md)
- [Module und Features](docs/module-und-feature-doku.md)
- [Roadmap](docs/roadmap.md)

## Hinweise

- Es wurden keine Inhalte entfernt; alle bisherigen README-Informationen wurden in thematisch getrennte Dateien unter `docs/` ausgelagert.
- Service-Setup bleibt unter `systemd/pixeldock32.service`.
