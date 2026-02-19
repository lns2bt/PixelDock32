# Module und Features

## Modul-Settings (UI)

In der Modul-Verwaltung können modul-spezifische Einstellungen direkt bearbeitet und gespeichert werden:

- **Clock**: `timezone`, Sekundenanzeige an/aus, einstellbarer `char_spacing`
- **BTC**: kompakte Anzeige im k-Format (z. B. `56.8k`), einstellbarer `char_spacing`
- **Weather**: Temperatur in Celsius (Stadtname ausgeblendet), optional Postleitzahl-Info, einstellbarer `char_spacing`
- **Text Box**: Zeilen-/Ticker-Text mit einstellbarem `char_spacing`

Die Werte werden über `PUT /api/modules/{id}` gespeichert.

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
- Beim **Clock-Modul** ist das Sekundentakt-Sliding standardmäßig deaktiviert (`transition_on_content_change=false`), damit der Slide primär beim Modulwechsel sichtbar ist.

## Clock-Sekundenrand

Das Clock-Modul unterstützt optional einen dynamischen 1px-Rand als Sekunden-Visualisierung:

- `seconds_border_mode=off`: deaktiviert
- `seconds_border_mode=linear`: linearer Fortschritt über die Minute
- `seconds_border_mode=two_forward_one_back`: animierter "2 vor, 1 zurück" Verlauf
- `seconds_border_mode=dual_edge`: zusätzlicher Modus mit Wachstum von zwei Startpunkten
- `seconds_border_color`: Farbe des Sekundenrands

Der Rand ist bei `0s` leer und bei `59s` vollständig gefüllt.

## Bitmap-Modul (32px breit, vertikales Scrolling)

- Modul **Bitmap** lädt Bitmap-Dateien aus `app/bitmaps/` (Monochrom **und RGB**).
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
