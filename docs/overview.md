# Projektüberblick

PixelDock32 ist ein modularer 8x32-Controller für 4x WS2812B-8x8 Panels. Der Raspberry Pi übernimmt API, Webserver und Datenbeschaffung; die LED-Signalerzeugung kann effizient per USB auf einen Arduino UNO R3 ausgelagert werden (oder optional direkt via GPIO18 + `rpi_ws281x`).

## Kurz-Architektur (MVP)

- **FastAPI API + Web UI** für Verwaltung und direkte Anzeige-Befehle.
- **SQLite** speichert Modul-Konfigurationen (`enabled`, `duration`, `order`, `settings`).
- **Render-Loop (async, non-blocking)** läuft im Hintergrund und rotiert aktive Module.
- **Hintergrund-Poller** holen BTC-Preis + Wetter zyklisch und cachen die Werte.
- **LED-Mapping Layer** übersetzt logische Koordinaten (x=0 links) auf physische Daisy-Chain (Datenstart rechts).
- **LED-Transport-Layer** sendet gerenderte Frames entweder an `rpi_ws281x` (GPIO) oder als kompaktes Binärprotokoll via USB-Serial an den Arduino UNO R3.
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
