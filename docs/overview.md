# Projektüberblick

PixelDock32 ist ein modularer 8x32-Controller für 4x WS2812B-8x8 Panels auf Raspberry Pi (GPIO18 + `rpi_ws281x`).

## Kurz-Architektur (MVP)

- **FastAPI API + Web UI** für Verwaltung und direkte Anzeige-Befehle.
- **SQLite** speichert Modul-Konfigurationen (`enabled`, `duration`, `order`, `settings`).
- **Render-Loop (async, non-blocking)** läuft im Hintergrund und rotiert aktive Module.
- **Hintergrund-Poller** holen BTC-Preis + Wetter zyklisch und cachen die Werte.
- **LED-Mapping Layer** übersetzt logische Koordinaten (x=0 links) auf physische Daisy-Chain (Datenstart rechts).
- **Auth** via Login + JWT für UI/API Schutz im LAN.

## Ordnerstruktur

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
