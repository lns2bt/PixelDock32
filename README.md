# PixelDock32

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

## Hardware-Mapping Hinweise

- Verkabelung: `GPIO18 -> rechtes Panel IN -> ... -> linkes Panel`.
- Standard-Config ist darauf ausgelegt:
  - `DATA_STARTS_RIGHT=true`
  - `SERPENTINE=true`
  - `FIRST_PIXEL_OFFSET=0`
- Logische API-Koordinaten bleiben immer **links nach rechts**.

## Setup

```bash
cd /path/to/PixelDock32
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Optional: Admin-Passwort in `.env` anpassen.

## Start

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Dann im LAN öffnen: `http://<raspberrypi-ip>:8000`

## API-Übersicht (MVP)

- `POST /api/auth/login` → JWT holen
- `GET /api/modules` → Module laden
- `PUT /api/modules/{id}` → Modul ändern
- `POST /api/display/text` → Sofort-Text anzeigen
- `POST /api/display/draw` → 8x32 Pixel-Frame anzeigen
- `POST /api/display/brightness` → Helligkeit setzen
- `POST /api/debug/pattern` → Kalibrier-/Debug-Pattern starten
- `DELETE /api/debug/pattern` → Debug-Pattern stoppen


## Panel-Kalibrierung & Hardware-Debug

Neue Debug-Pattern helfen beim Verkabeln und Mapping-Check:

- `pixel_walk`: wandert Pixel für Pixel durch das 8x32 Feld
- `panel_walk`: schaltet panelweise 8x8 Blöcke
- `stripes`: blinkende vertikale Streifen
- `border`: statischer Rahmen

Über die Web-UI im Abschnitt **Hardware-Debug / Kalibrierung** oder per CLI:

```bash
python3 scripts_calibrate.py --pattern pixel_walk --seconds 30 --interval-ms 200
```

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

## Nächste sinnvolle Schritte

1. **Panel-Kalibrierungstest**: kleines Testscript für Pixel-Walk + Mapping-Verifikation je Panel.
2. **Module-Settings UI**: pro Modul JSON-Settings im Frontend editierbar machen.
3. **Bessere Text-Engine**: Scrolling + größere Font-Auswahl + UTF-8 Glyphen.
4. **API-Resilience**: Retry/Backoff + sichtbarer Status in UI (letztes Update, Fehlerzustand).
5. **Sicherheits-Hardening**: HTTPS via Reverse Proxy, rate limit, Passwort-Hash verpflichtend.
