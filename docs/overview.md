# Project overview

PixelDock32 is a modular 8x32 controller for 4x WS2812B-8x8 panels. The Raspberry Pi handles API, web server and data retrieval; The LED signal generation can be efficiently outsourced to an Arduino UNO R3 via USB (or optionally directly via GPIO18 + `rpi_ws281x`).

## Short Architecture (MVP)

- **FastAPI API + Web UI** for administration and direct display commands.
- **SQLite** stores module configurations (`enabled`, `duration`, `order`, `settings`).
- **Render loop (async, non-blocking)** runs in the background and rotates active modules.
- **Background pollers** fetch BTC price + weather cyclically and cache the values.
- **LED Mapping Layer** translates logical coordinates (x=0 left) to physical daisy chain (data start right).
- **LED transport layer** sends rendered frames either to `rpi_ws281x` (GPIO) or as a compact binary protocol via USB serial to the Arduino UNO R3.
- **Auth** via login + JWT for UI/API protection on the LAN.

## Folder structure

```text
app/
  api/            # FastAPI Endpunkte
  modules/        # Anzeige-Module (Clock, BTC, Weather)
  services/       # Render-Loop, Polling, LED Driver, Mapping
  static/         # Web UI (HTML/CSS/JS)
  config.py       # .env Settings
  database.py     # SQLAlchemy Engine/Session
  models.py       # DB Modelle
  schemas.py      # API Schemas
  main.py         # App Entry + Startup/Lifespan
systemd/
  pixeldock32.service
.env.example
requirements.txt
```
