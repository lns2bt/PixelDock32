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
- `GET /api/debug/status` → Laufzeit-/Debug-Status (FPS, aktive Quelle, Polling-Stand)
- `GET /api/debug/preview` → aktueller 8x32 Frame für virtuelle Vorschau
- `GET /api/debug/mapping/coordinate?x=&y=` → Mapping-Erklärung für einzelne Koordinate


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


## Modul-Settings (UI)

In der Modul-Verwaltung können jetzt modul-spezifische Einstellungen direkt bearbeitet und gespeichert werden:

- **Clock**: `timezone`, Sekundenanzeige an/aus
- **BTC**: kompakte Anzeige im k-Format (z. B. `56.8k`)
- **Weather**: Temperatur in Celsius (Stadtname ausgeblendet), optional Postleitzahl-Info

Die Werte werden über `PUT /api/modules/{id}` gespeichert.


## Mapping-Wizard & Virtuelle Vorschau


Die Web-UI enthält jetzt einen geführten Mapping-Bereich mit:

- Schritt-Buttons für Panel-Reihenfolge/Serpentine/Rand-Check
- Koordinaten-Inspektor (`x`,`y`) mit Rückgabe des physikalischen LED-Index
- Virtuelle Live-Vorschau (8x32) über `GET /api/debug/preview`

Damit kannst du Mapping-Fehler systematisch finden, ohne nur auf das physische Panel schauen zu müssen.


## Farb-Logik der Module

- **BTC**: Führendes `B` ist orange. Preis in `k`-Format wird grün bei steigendem Kurs, rot bei fallendem Kurs, gelb bei unverändert.
- **Weather**: Temperatur wird farbcodiert von kalt (blau) bis warm (rot) angezeigt.
- **Virtuelle Vorschau**: zeigt diese Farben live über `GET /api/debug/preview` an.

## Multiline & Transition-Animation

- Neues Modul **Text Box** für kurze mehrzeilige Texte (`lines`) mit automatischem Zeilenwechsel (`line_seconds`).
- Alle Text-Module unterstützen vertikale Transitionen bei Inhaltswechsel:
  - `transition_direction=down` (neue Zeile von oben nach unten)
  - `transition_direction=up` (neue Zeile von unten nach oben)
- Übergangsdauer über `transition_ms` einstellbar (0 = ohne Animation).

## Bitmap-Modul (32px breit, vertikales Scrolling)

- Neues Modul **Bitmap** lädt Bitmap-Dateien aus `app/bitmaps/` (Monochrom **und RGB**).
- Unterstützte Formate:
  - Plaintext-Bitmaps (`0/1`, `#`, `X`, `@`)
  - Plaintext-Farb-Token pro Pixel (z. B. `#RRGGBB`, `r:g:b`, `0xRRGGBB`, `off`)
  - `P1`-PBM (Monochrom)
  - `P3`-PPM (RGB)
- Erwartete Breite: **32 Pixel**. Höhe darf größer als 8 sein.
- Bei Höhe `> 8` wird ein 8-Zeilen-Fenster vertikal gescrollt:
  - `scroll_direction=top_to_bottom`
  - `scroll_direction=bottom_to_top`
- Scroll-Geschwindigkeit über `scroll_speed` (empfohlen 0.25 bis 20).

Beispiel-Files: `app/bitmaps/sample_arrow.txt` (mono) und `app/bitmaps/sample_gradient.ppm` (RGB)


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
2. **Mapping-Wizard**: geführte Kalibrierung für Panel-Reihenfolge, Serpentine und Offset.
3. **Bessere Text-Engine**: Scrolling + größere Font-Auswahl + UTF-8 Glyphen.
4. **API-Resilience**: Retry/Backoff + sichtbarer Status in UI (letztes Update, Fehlerzustand).
5. **Sicherheits-Hardening**: HTTPS via Reverse Proxy, rate limit, Passwort-Hash verpflichtend.


## UI/UX Verbesserungen (Sprint A)

- Globales **System-Status Panel** in der Web-UI (API online, Quelle, Modul, FPS, Debug-Status, Daten-Updates).
- **Toast-Feedback** bei allen UI-Aktionen inklusive Fehlern/Netzwerkproblemen.
- **Quick Presets** für Debug-Pattern (Wiring/Serpentine/Noise Check).
- Neues Backend-Status-API: `GET /api/debug/status`.


## Troubleshooting

Wenn beim Start folgender Fehler kommt:

- `ValueError: the greenlet library is required to use this function. No module named "greenlet"`

Dann wurden die Python-Abhängigkeiten unvollständig installiert. Neu installieren:

```bash
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Danach `uvicorn app.main:app --host 0.0.0.0 --port 8000` erneut starten.


## GIF-Support (Roadmap)

Aktuell rendert das Bitmap-Modul statische Dateien mit vertikalem Scrolling. Für kleine GIF-Animationen sind als nächster Schritt nötig:

- Frame-Decoder (z. B. `Pillow`) zum Extrahieren einzelner GIF-Frames inkl. Frame-Dauer.
- In-Memory-Framecache (pro Datei + `mtime`) analog zum Bitmap-Cache.
- Zeitbasierte Frame-Auswahl im Renderloop (`now -> frame_index`) mit sauberem Looping.
- Optionales Dithering/Farbreduktion für bessere Lesbarkeit auf 32x8.
- Einheitliche Einstellungen im Modul (`playback_speed`, `loop_mode`, optional `fit/crop`).
