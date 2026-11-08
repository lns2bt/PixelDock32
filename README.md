# PixelDock32

![Version](https://img.shields.io/badge/version-0.5.0-blue)
![Status](https://img.shields.io/badge/status-release-brightgreen)


PixelDock32 is a modular 8x32 controller for 4x WS2812B-8x8 panels. By default, the Raspberry Pi renders the data and transfers frames efficiently via USB serial to an Arduino UNO R3, which generates the WS2812B signal (GPIO18 + `rpi_ws281x` remains optional).

See [`docs/`](docs) for setup, architecture, hardware, and feature guides.

## Features

**Time-Stage**: 30 clock views, 10 magical event animations,
independent clock scheduling, sleep mode and local sun/moon ceremonies.
Details: [Time-Stage](docs/time-stage.md).

**Bitcoin-Stage**: ten coherent pixel styles for seven equally rotated information types,
with at most two per presentation by default, dedicated settings and previews
under `/bitcoin`. Details: [docs/bitcoin-stage.md](docs/bitcoin-stage.md).

**Weather-Stage**: four coherent pixel styles for outdoor/indoor temperature,
indoor humidity, and current conditions. Configure scenes, rotation, and previews
at `/weather`. Open-Meteo model data and local indoor readings have independent
freshness indicators: [Weather-Stage](docs/weather-stage.md).

**Smooth motion**: Pi-side gamma correction without firmware
changes, nine eased transitions, 15 anti-aliased animations, rolling clock
digits and a clearer Weather-Stage card. Details:
[Modules and features](docs/modules-and-features.md#smooth-motion-pipeline).

The display targets 30 FPS using Uno firmware v3. Existing `.env` settings are
preserved. Firmware compatibility and brightness synchronization:
[Phase 2](docs/rework-phase2.md).
For development without hardware, explicitly use `LED_TRANSPORT=mock`.

The dashboard includes a collapsible live preview, sortable playlist with
priority/shuffle slots, GIF/PNG import, and a sprite editor with range trimming,
timing-preserving frame thinning, and three GIF playback modes
([GIF editing](docs/gif-editing.md)). Diagnostics are grouped under **Advanced**.

Pi deployments retain settings, modules, assets, and mapping. Substantial updates
use a separate directory with a private backup and rollback instructions.

## Version 0.5.0 — Clocks and redesign

Smoother clocks with six digit change styles and five new scenes (Newton's
Cradle, Live Sky, Nixie Tubes, Weather Clock, Aquarium), plus a redesigned web
interface: control-centre home page, compact playlist, tabbed clock settings and
a mobile tab bar. See the [changelog](CHANGELOG.md) for details.

- Current version: [`0.5.0`](VERSION)
- Release notes: [`CHANGELOG.md`](CHANGELOG.md)
- Release tag: `v0.5.0` (planned, after merge to `main`)

## Quick start

```bash
cd /path/to/PixelDock32
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# only required on Raspberry Pi with DHT sensor:
pip install Adafruit_DHT==1.4.0 --config-settings="--build-option=--force-pi"
# Alternative (if Adafruit_DHT/platform discovery fails):
pip install adafruit-circuitpython-dht adafruit-blinka
# optional GPIO backend fallback:
# lgpio from pip needs build tools AND the native lgpio library
sudo apt update && sudo apt install -y swig python3-dev liblgpio-dev
pip install lgpio
# Alternative without pip build (system package):
# sudo apt install -y python3-lgpio
cp .env.example .env
# Recommended for Arduino USB transport:
# LED_TRANSPORT=serial
# LED_SERIAL_PORT=auto
# LED_SERIAL_ACK_TIMEOUT=0.05
# Firmware v3 recommended; v2 only has frame ACK, v1 is no longer controlled
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open on LAN: `http://<raspberrypi-ip>:8000`

## Documentation

- [Project Overview & Architecture](docs/overview.md)
- [Setup, operation, .env, and troubleshooting](docs/setup-and-operation.md)
- [Raspberry Pi autostart + recovery in case of hangs](docs/autostart-raspberry-pi.md)
- [API Overview](docs/api.md)
- [Hardware, mapping, calibration, Arduino Uno R3, and DHT11](docs/hardware-and-mapping.md)
- [Modules and features](docs/modules-and-features.md)
- [Roadmap](docs/roadmap.md)
- [Rework analysis](docs/rework-analysis.md)
- [Local tests and passive transport measurements](docs/tests-and-measurements.md)

## Notes

- Older architecture/rework notes describe their historical development stage.
- Service setup remains under `systemd/pixeldock32.service`.
