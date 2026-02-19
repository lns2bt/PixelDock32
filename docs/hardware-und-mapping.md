# Hardware, Mapping und Kalibrierung

## Hardware-Mapping Hinweise

- Verkabelung: `GPIO18 -> rechtes Panel IN -> ... -> linkes Panel`.
- Standard-Config ist darauf ausgelegt:
  - `DATA_STARTS_RIGHT=true`
  - `SERPENTINE=true`
  - `FIRST_PIXEL_OFFSET=0`
  - `PANEL_ORDER=0,1,2,3`
  - `PANEL_ROTATIONS=0,0,0,0`
- Logische API-Koordinaten bleiben immer **links nach rechts**.

## Schnelles Mapping-Schema

Wenn Panels verdreht oder vertauscht montiert wurden, kannst du das mit zwei Werten korrigieren:

- `PANEL_ORDER`: Reihenfolge der **physisch verketteten Panels** auf die logischen Panel-Slots.
  - Format: Komma-Liste mit 4 Zahlen (`0..3`)
  - Beispiel `3,2,1,0`: komplett gespiegelt
- `PANEL_ROTATIONS`: Rotation je **logischem Panel-Index** in Grad.
  - Erlaubt: `0`, `90`, `180`, `270`
  - Beispiel `0,180,0,180`: jedes zweite Panel auf dem Kopf

Empfohlener Ablauf:

1. `panel_walk` nutzen, bis die Reihenfolge passt (`PANEL_ORDER`).
2. Danach mit `pixel_walk` die Laufrichtung prüfen und pro Panel die Rotation setzen (`PANEL_ROTATIONS`).
3. Optional mit `border` final gegenprüfen.

So kannst du typische Hardware-Fehler mit wenigen Zahlenwerten beheben, ohne Code anzufassen.

## Panel-Kalibrierung & Hardware-Debug

Debug-Pattern für Verkabelung und Mapping-Check:

- `pixel_walk`: wandert Pixel für Pixel durch das 8x32 Feld
- `panel_walk`: schaltet panelweise 8x8 Blöcke
- `stripes`: blinkende vertikale Streifen
- `border`: statischer Rahmen

Über die Web-UI im Abschnitt **Hardware-Debug / Kalibrierung** oder per CLI:

```bash
python3 scripts_calibrate.py --pattern pixel_walk --seconds 30 --interval-ms 200
```

## Mapping-Wizard & Virtuelle Vorschau

Die Web-UI enthält einen geführten Mapping-Bereich mit:

- Schritt-Buttons für Panel-Reihenfolge/Serpentine/Rand-Check
- Koordinaten-Inspektor (`x`,`y`) mit Rückgabe des physikalischen LED-Index
- Virtuelle Live-Vorschau (8x32) über `GET /api/debug/preview`

Damit kannst du Mapping-Fehler systematisch finden, ohne nur auf das physische Panel schauen zu müssen.

## DHT11 am Raspberry Pi (lokale Temperatur + Luftfeuchte)

Das Weather-Modul kann optional direkt vom DHT-Sensor lesen (statt Open-Meteo):

1. Verdrahtung DHT11
   - VCC -> 3.3V (Pin 1)
   - GND -> GND (z. B. Pin 6)
   - DATA -> GPIO4 (Pin 7, anpassbar über `DHT_GPIO_PIN`)
   - Bei nacktem Sensor: 10k Pull-Up zwischen DATA und VCC
2. Python-Bibliothek installieren:

   Hinweis: Falls `RPi.GPIO` fehlt, zuerst das OS-Paket für dein Raspberry-Pi-System installieren (z. B. `python3-rpi-gpio` oder je nach Distribution `python3-rpi-lgpio`).
   ```bash
   pip install -r requirements.txt
   pip install Adafruit_DHT==1.4.0 --config-settings="--build-option=--force-pi"
# Alternative (falls Adafruit_DHT/Plattform-Erkennung fehlschlägt):
pip install adafruit-circuitpython-dht adafruit-blinka
# optionaler GPIO-Backend-Fallback (v. a. bei Python 3.13):
pip install lgpio
   ```
3. In `.env` aktivieren:
   ```env
   DHT_ENABLED=true  # default aktiv
   DHT_MODEL=DHT11
   DHT_GPIO_PIN=4
   POLL_DHT_SECONDS=3
   ```

Hinweise:
- Das Weather-Modul rotiert kompakt zwischen 3 Screens: `Oxx.xC` (Outdoor), `Ixx.xC` (Indoor), `Hxx%` (Indoor Luftfeuchte).
- Die Umschaltzeit ist im Modul über `Screen-Wechsel (Sek.)` einstellbar.
- Datenquellen: Outdoor aus Open-Meteo, Indoor/Feuchte aus DHT11.

### Kurz erklärt: Signalverarbeitung & GPIO (DHT11 ↔ Raspberry Pi)

- **Leitung/Protokoll:** Der DHT11 nutzt eine einzelne **DATA-Leitung** (Single-Wire, proprietäres Timing-Protokoll).
- **GPIO-Belegung:** In diesem Projekt hängt DATA standardmäßig auf **BCM GPIO4** (`DHT_GPIO_PIN=4`), Versorgung über **3.3V** und **GND**.
- **Signalstabilität:** Ein **Pull-Up (typisch 10kΩ)** zwischen DATA und 3.3V hält das Signal im Idle-Zustand auf HIGH.
- **Messablauf in der App:** Der DHT-Poller in `ExternalDataService` ruft zyklisch `Adafruit_DHT.read_retry(...)` auf. Die Library erzeugt die nötigen Timing-Sequenzen am GPIO und dekodiert daraus Temperatur/Feuchte.
- **Weiterverarbeitung:** Die dekodierten Werte werden als `weather_indoor_temp` und `weather_indoor_humidity` im Cache abgelegt; Open-Meteo bleibt separat als `weather_outdoor_temp`.
- **Anzeige:** Das Weather-Modul schaltet zeitgesteuert zwischen Outdoor-Temp, Indoor-Temp und Indoor-Feuchte um.
