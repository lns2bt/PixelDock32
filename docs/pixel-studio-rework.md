# Pixel-Studio und Dashboard-Rework

## Stand und Umfang

Der geprüfte Stand wurde von `rework/smooth-led-pipeline` nach `main` übernommen.
Der Softwarestand `1227bfa` läuft auf dem Pi in
`/home/david/PixelDock32-controls-1227bfa`, einschließlich Helligkeit, verbessertem
Login-Kontrast und neuen Uhr-/Bitcoin-Darstellungen. Firmware v3 bleibt unverändert.
Frühere Projektverzeichnisse und Sicherungen bleiben erhalten. Kein Langzeit-Hardwaretest.

`pixeldock32.service` und `pixeldock32-healthcheck.timer` sind für den Systemstart
aktiviert. Der dauerhafte Drop-in
`/etc/systemd/system/pixeldock32.service.d/90-rework-test.conf` zeigt auf das aktuelle
Projekt und dessen eigene venv/`.env`. Trotz des historischen Dateinamens ist dies
eine persistente Konfiguration, keine temporäre Test-Unit. Kein Neustart des Pi war
für diese Bestätigung nötig; ein erneuter Boot-Test wurde nicht durchgeführt.

Neue Hauptseiten:

- `/`: dunkles Dashboard mit Live-Daten, Playlist und schneller Textnachricht.
- `/modules`: mehrere Instanzen bestehender Module, Duplizieren, Aktivieren,
  Einstellungen, Drag-and-drop und Hoch-/Runter-Tasten. Reihenfolge wird in einer
  Transaktion gespeichert. Ungespeicherte Formularänderungen werden angekündigt.
- `/studio`: GIF/PNG-Import, 32×8-Pixel-Editor mit mehreren Frames, Farbe/Radierer,
  Undo, Duplizieren, Sortieren, Frame-Timing und vorherigem Frame als Zeichenhilfe.
- `/advanced`: bestehende Diagnose, Mapping und weitere Werkzeuge. Diese Seiten
  sind erhalten, nicht gelöscht. Die ursprünglichen statischen Dashboard- und
  Moduldateien bleiben ebenfalls erhalten, werden aber nicht mehr als Hauptseiten
  ausgeliefert.

Eine sticky Kopfzeile zeigt auf allen angemeldeten Seiten die gerenderte Matrix.
Die Vorschau ist **kein physisches Kamerabild und keine Bestätigung eines Frames**.
Sie wird höchstens ungefähr fünfmal pro Sekunde passiv abgerufen; Status etwa alle
fünf Sekunden. Keine parallelen Polls und Pause bei verborgenem Tab. Keine zusätzlichen
Serial-Probes, keine externen Fonts, CDN-Skripte oder Grafikdienste.

## Assets und Grenzen

`ASSET_DIRECTORY=data/assets` (relativ zum Arbeitsverzeichnis) ist ein eigener
privater Datenspeicher, nicht das öffentlich ausgelieferte Static-Verzeichnis.
Dieses Verzeichnis künftig zusammen mit Datenbank, Mapping und `.env` sichern.
Es ist in `.gitignore` ausgeschlossen.

- Pillow **12.3.0**, auch als ARM64-Wheel für Python 3.13 verfügbar.
- GIF und PNG; Nearest-Neighbor, mittiges Einpassen/Zuschneiden oder Strecken.
- Transparenz wird auf Schwarz zusammengesetzt. GIF-Frames werden von Pillow
  inklusive Compositing/Disposal verarbeitet und anschließend vorab dekodiert.
- Maximal 4 MB Upload, 1024 Pixel je Seite, 262144 Pixel pro Quellframe,
  8 Millionen dekodierte Quellpixel und 120 Frames. Frame-Timing: 33–2000 ms.
- Sprite-JSON: maximal 512 KB, 1–120 Frames, exakt 256 RGB-Integer je Frame.
- Bibliothek maximal 128 Assets einschließlich der drei Beispiele.
- RAM-Cache maximal acht Assets; der laufende Slot hält zusätzlich seine aktuelle
  Referenz. Rendering braucht keine wiederholten Dateizugriffe oder Bilddekodierung.
- Asset-IDs werden validiert; Import, Bibliothek und Änderungen erfordern Anmeldung.
  Asset-Löschen wird verhindert, solange ein Modul darauf verweist.
- Editor-Speichern erzeugt eine **neue Kopie**, keine stille Änderung der laufenden
  Module. Die Kopie kann als Modul hinzugefügt oder einem bestehenden Asset-Modul
  zugeordnet werden.

Die eigenen Beispiele **Rooftop Runner**, **Coin Quest** und **Starship Patrol**
werden einmalig mit stabilen IDs angelegt. Keine fremden Spielgrafiken enthalten.

## Playlist und LED-Darstellungen

Bestehende DB-Struktur bleibt erhalten; neue Instanzen haben eindeutige Keys wie
`asset-<id>` oder `clock-<id>`. Einstellungen bleiben im vorhandenen JSON-Feld.
Keine Migration oder automatische Umschreibung vorhandener Nutzerkonfigurationen.

- Normale Module: feste Reihenfolge.
- `shuffle=true`: zufälliger Einwurf nach drei normalen Slots, nicht zufällige
  Veränderung der normalen Reihenfolge. Bei ausschließlich Shuffle-Modulen werden
  diese nacheinander zufällig ausgewählt; unmittelbare Wiederholung wird vermieden,
  soweit es mehr als ein Modul gibt.
- `priority_every`: frühestens nach diesem Intervall an einer Slot-Grenze erneut
  einblenden. Standard für Uhr: **45 Sekunden**, Dauer standardmäßig **8 Sekunden**.
  Ein normaler Uhr-Auftritt setzt das Intervall ebenfalls zurück. Die tatsächliche
  Einblendung kann später erfolgen, wenn noch Inhalt läuft.
- GIF-/Sprite-Loops und vollständige Text-Scrollsequenzen laufen zu Ende. Die
  eingestellte Slot-Dauer wird auf eine vollständige Loop-Länge aufgerundet.
  Bei langen Assets oder stark verlangsamter Wiedergabe wartet auch die Uhr länger.
- „Jetzt“ spielt ein Modul einmalig und kehrt danach mit einem neuen Slot zur
  Playlist zurück. Aus der Bibliothek wird nötigenfalls ein deaktiviertes Modul
  angelegt; die normale Playlist wird dadurch nicht automatisch erweitert.
- Bestehende Standardmodule bitte deaktivieren; ihre zusätzlichen Instanzen können
  gelöscht werden. Maximal 128 Module.
- Übergänge: sanfter Crossfade, Pixel-Dissolve, vertikaler Slide oder keine.
  Übergänge werden nur bei Modul-/Ansichtswechseln ausgelöst, niemals pro
  Animationsframe neu gestartet. API/UI erlauben 0–2000 ms.

Uhransichten: klassische Ziffern, Arcade-Figur mit Sekunden-Coin, Sekundenbalken,
Binärakzente, Neon-Orbit, Neon-Ziffern/Sternenflug und Pixel-Flip. **Genau eine Ansicht
pro Uhr-Auftritt**; die aktivierten Ansichten rotieren erst beim nächsten Auftritt
(regulär, priorisiert oder „Jetzt“). Das frühere `variant_seconds` wird nicht mehr
verwendet. Die Animation innerhalb der ausgewählten Ansicht läuft weiter. Wetter/Raumklima
haben Sonne, Haus und Tropfen als temperatur-/feuchtigkeitsbezogene Symbole – die Sonne
ist **keine Wetterzustandsprognose**. Bitcoin hat ein pulsierendes Coin-Symbol und
Trendfarben. `visual_style=legacy` erhält bei Bedarf die früheren Textdarstellungen.

## Prüfung

```sh
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m unittest discover -s tests -v
node --check app/static/shell.js
node --check app/static/arcade.js
```

Hardwarefreie Tests decken Import, RGB/Timing, Grenzen, Pfadsicherheit, Authentifizierung,
CRUD, Reihenfolge, Shuffle, Priorität, vollständige Loops, einmalige Wiedergabe,
Uhrvarianten und Übergänge ab. Zusätzlich lokaler Chromium-Browsertest auf Desktop
und 390-Pixel-Mobilansicht: sticky Vorschau, Formulare, Reihenfolge, Zeichnen,
Frame-Duplizieren, Bibliothek und einmalige Wiedergabe. Keine echte Hardware bei
diesen Tests angesprochen.

Aktueller lokaler Stand: **95 Tests erfolgreich**, Browser-Smoke ebenfalls erfolgreich.

## Helligkeit und Kontrast

- Sonnensymbol im Header aller angemeldeten Seiten, ohne Suche in Diagnosewerkzeugen.
- Exponentielle Reglerkennlinie `round(exp(log(256) * position / 1000) - 1)`.
  Die niedrigen Werte 0–10 belegen rund 43 % des Wegs; Ganzzahl, ±1-Tasten und
  Schnellwerte 0/1/3/6/12 ermöglichen exaktes Einstellen. Draggen verändert zunächst
  den UI-Wert; angewendet wird beim Loslassen. Zahl und Tasten wirken sofort.
- Helligkeit wird in der zusätzlichen Tabelle `display_preferences` gespeichert;
  vorhandene Tabellen/Module werden nicht umgeschrieben. Fehlt ein gespeicherter Wert,
  gilt weiterhin `LED_BRIGHTNESS` aus `.env`. Auch **0** wird korrekt wiederhergestellt.
- Hardwarezugriffe bleiben off-thread und serialisiert. Bei nicht erreichbarem Uno
  bleibt der Zielwert gespeichert und wird bei Wiederverbindung angewendet.
- Der Login hat jetzt explizit dunkle Hintergründe, helle Beschriftungen/Platzhalter
  und sichtbare Fokusrahmen. Browser-Smoke prüft mindestens **4,5:1** Textkontrast.
- Bitcoin: besser erkennbares ₿ mit B-Schleifen und Doppelstrichen, eigener pulsierender
  Symbolfarbe, getrennten Trendfarben und Richtungspfeil. Preise ab einer Million Euro
  verwenden `M` statt einer abgeschnittenen Darstellung mit `k`.

Reproduzierbarer Browser-Smoke-Test (lokal, niemals gegen den laufenden Pi):

```sh
# Terminal 1: eigene temporäre Daten und ausschließlich Mock-Hardware
TMPDIR=/tmp/opencode .venv/bin/python scripts/ui-test-server.py
# Terminal 2: Playwright außerhalb des Projektverzeichnisses installieren
npm install --prefix /tmp/opencode/pixeldock-browser playwright@1.64.0
NODE_PATH=/tmp/opencode/pixeldock-browser/node_modules node scripts/ui-smoke.cjs
```

Der Test nutzt `/usr/bin/chromium`, falls vorhanden, sonst den Playwright-Browser;
bei Bedarf `CHROMIUM_PATH` setzen.
`PIXELDOCK_UI_ARTIFACTS` aktiviert optionale Screenshots. Vor Änderungen prüft
der Test, dass die Anwendung wirklich das Mock-Backend benutzt.

## Spätere Pi-Installation

Erst nach Freigabe einen **weiteren separaten Teststand** anlegen; aktuelle Rework-DB,
`.env`, Mapping und Assets unmittelbar vorher sichern/kopieren. Die aktuelle Anwendung
nicht in-place überschreiben. Neue Abhängigkeit nur in der neuen venv installieren.
Den bestehenden Dienst-Drop-in gezielt umstellen, Healthcheck kurz pausieren und
vorherigen Stand für Rückwechsel behalten. Für dieses Rework ist **kein Firmware-Flash**
nötig. Bestehende Uhr-/Animations-Einstellungen (z.B. `transition_ms=0`) bleiben
wirksam und können im neuen Formular angepasst werden.
