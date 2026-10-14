# PixelDock32

![Version](https://img.shields.io/badge/version-0.2.0-blue)
![Status](https://img.shields.io/badge/status-release-brightgreen)


PixelDock32 ist ein modularer 8x32-Controller für 4x WS2812B-8x8 Panels. Standardmäßig rendert der Raspberry Pi die Daten und überträgt Frames effizient per USB-Serial an einen Arduino UNO R3, der das WS2812B-Signal erzeugt (optional bleibt GPIO18 + `rpi_ws281x`).

Das README ist bewusst kurz gehalten. Die ausführliche, aufgeteilte Projektdokumentation liegt unter [`/docs`](docs).

## Aktueller Standard: Datenweg, Dashboard und Pixel-Studio

**Time-Stage**: 20 Uhransichten, 10 magische Ereignisanimationen,
eigenständige Uhr-Regie, Schlafmodus und lokale Sonnen-/Mondzeremonien.
Details: [Time-Stage](docs/time-stage.md).

**Bitcoin-Stage**: zehn gemeinsame Pixelstile für sieben gleichberechtigte Infos,
standardmäßig höchstens zwei pro Vorstellung, mit eigenen Einstellungen und Vorschauen
unter `/bitcoin`. Details: [docs/bitcoin-stage.md](docs/bitcoin-stage.md).

**Wetter-Stage**: vier gemeinsame Pixelstile für Außentemperatur, Innentemperatur,
Innenfeuchtigkeit und aktuelle Wetterbedingungen. Szenen, Rotation und direkte
Vorschauen unter `/weather`. Modellbasierte Open-Meteo-Außendaten und lokale
Innenmessung mit getrenntem Datenstatus: [Wetter-Stage](docs/weather-stage.md).

Dieser Zweig enthält den überarbeiteten 30-FPS-Datenweg und Uno-Firmware v3.
Vorhandene `.env`-Werte werden nicht überschrieben. Für vollständige
Helligkeits-Synchronisation ist die neue Firmware vorgesehen; Details und
Kompatibilitätsgrenzen: [Phase 2](docs/rework-phase2.md).
Für Entwicklung ohne Hardware explizit `LED_TRANSPORT=mock` verwenden.

Das Dashboard bietet jetzt eine einklappbare Live-LED-Vorschau, eine sortierbare
Playlist mit Prioritäts-/Shuffle-Slots sowie GIF-/PNG-Import und einen Sprite-Editor
mit Bereichskürzung, zeitgetreuem Ausdünnen und drei GIF-Wiedergabemodi
([GIF-Bearbeitung](docs/gif-editing.md)). Uhransichten, Modulsymbole und Übergänge wurden überarbeitet;
Diagnosewerkzeuge sind unter „Erweitert“ gebündelt.

Der geprüfte Stand mit Firmware v3, Pixel-Studio, Time-Stage, Bitcoin-Stage und
kompakter Oberfläche mit direkten LED-Vorschauen ist auf dem Pi installiert und als
Autostart eingerichtet. `main` enthält diesen Standardstand; die früheren Pi-Stände
und Sicherungen bleiben für einen Rückwechsel erhalten. Umfang und Testanleitung:
[Pixel-Studio-Rework](docs/pixel-studio-rework.md).

## Version 0.2.0 — Pixel-Studio und Szenen-Stages

Dieser auf dem Pi geprüfte Stand umfasst GIF-Bearbeitung, Time-Stage,
Bitcoin-Stage und Wetter-Stage mit kompakter Oberfläche und direkten Vorschauen.

- Aktuelle Version: [`0.2.0`](VERSION)
- Release-Notizen: [`CHANGELOG.md`](CHANGELOG.md)
- Release-Tag: `v0.2.0` auf `main`

## Schnellstart

```bash
cd /path/to/PixelDock32
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# nur auf Raspberry Pi mit DHT-Sensor erforderlich:
pip install Adafruit_DHT==1.4.0 --config-settings="--build-option=--force-pi"
# Alternative (falls Adafruit_DHT/Plattform-Erkennung fehlschlägt):
pip install adafruit-circuitpython-dht adafruit-blinka
# optionaler GPIO-Backend-Fallback:
# lgpio aus pip braucht Build-Tools UND die native lgpio-Library
sudo apt update && sudo apt install -y swig python3-dev liblgpio-dev
pip install lgpio
# Alternative ohne pip-Build (Systempaket):
# sudo apt install -y python3-lgpio
cp .env.example .env
# Für Arduino-USB-Transport empfohlen:
# LED_TRANSPORT=serial
# LED_SERIAL_PORT=auto
# LED_SERIAL_ACK_TIMEOUT=0.05
# Firmware v3 empfohlen; v2 hat nur Frame-ACK, v1 wird nicht mehr angesteuert
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Im LAN öffnen: `http://<raspberrypi-ip>:8000`

## Dokumentation

- [Projektüberblick & Architektur](docs/overview.md)
- [Setup, Betrieb, .env und Troubleshooting](docs/setup-und-betrieb.md)
- [Raspberry Pi Autostart + Recovery bei Hängern](docs/autostart-raspberry-pi.md)
- [API-Übersicht](docs/api.md)
- [Hardware, Mapping, Kalibrierung, Arduino UNO R3 & DHT11](docs/hardware-und-mapping.md)
- [Module und Features](docs/module-und-feature-doku.md)
- [Roadmap](docs/roadmap.md)
- [Rework-Analyse](docs/rework-analyse.md)
- [Lokale Tests und passive Transportmessung](docs/tests-und-messungen.md)

## Hinweise

- Es wurden keine Inhalte entfernt; alle bisherigen README-Informationen wurden in thematisch getrennte Dateien unter `docs/` ausgelagert.
- Service-Setup bleibt unter `systemd/pixeldock32.service`.
