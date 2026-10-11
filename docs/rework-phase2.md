# Phase 2: stabilisierter Uno-Datenweg

## Was sich ändert

- Standard jetzt **30 FPS**; eine vorhandene `.env` mit `RENDER_FPS=20` bleibt
  unverändert wirksam. Das ist ein Zielwert, noch kein Hardware-Messnachweis.
- Renderloop verwendet fortlaufende monotone Deadlines und überspringt verpasste
  Termine, statt nach einem Aussetzer alte Frames als Burst nachzuliefern.
- Ablaufzeiten, Modulrotation, Scrollen und Übergangsfortschritt verwenden monotone
  Zeit. Uhrzeit, Wetter-/BTC-Zeitstempel und UI-Endzeitstempel bleiben Kalenderzeit.
- Initiales schwarzes Bild und Änderungen am Mapping werden tatsächlich gesendet.
- Modulübergänge behalten ihre Zeitachse, auch wenn das eingehende Bild animiert
  ist. Animationen, Bitmaps und Laufschrift lösen nicht bei jedem Frame einen
  neuen Inhaltsübergang aus.
- Web-Endpunkte für LED-Diagnose, Ping, Helligkeit und Sensor-/GPIO-Operationen
  führen blockierende Arbeit in Workerthreads aus. Hardwarezugriffe auf die
  serielle Verbindung bleiben durch denselben I/O-Lock exklusiv serialisiert.
  Es gibt weiterhin einen Frame-Senderthread, **keinen vollständig neuen
  Kommando-Dispatcher**. DHT-Einzelreads und Poller teilen einen Sensor-Lock.
- Normales Status-Polling löst keine neue serielle Geräteabfrage mehr aus.
- Fehlendes USB-Gerät bleibt ein sichtbar getrenntes Serial-Backend mit Reconnect,
  statt dauerhaft auf Mock auszuweichen. `auto` bevorzugt nun Serial unabhängig
  von installierten GPIO-Paketen. Für Entwicklung explizit `LED_TRANSPORT=mock`.
- Fehlgeschlagene statische Frames werden ohne neue Browser-/Renderaktion erneut
  versucht. Neue wartende Frames haben weiterhin Vorrang; Retry/Reconnect haben
  einen konfigurierbaren Abstand (`LED_SERIAL_RECONNECT_DELAY`, Standard 1 s).
- Während einer statischen Anzeige prüft der Sender nach ungefähr 2 s ohne
  Verkehr den Firmwarestatus. USB-Ausfall, leerer Frame-Zähler nach Reset und
  abweichende Helligkeit lösen den Wiederabgleich aus. Während laufender
  Animation gibt es keine zusätzlichen periodischen Statuspakete.
- Transport-Shutdown stoppt Retry-Wartezeiten, beendet den Sender und schließt
  erst danach den Port. FastAPI räumt auch nach Initialisierungsfehlern auf.
- Kurze Serial-Writes und widersprüchliche Antwortlängen werden abgewiesen.
- Serial/auto validieren die feste Uno-Geometrie: 256 LEDs / 32×8.

## Firmware-Protokoll v3

RGB-Vollbilder und Frame-ACK bleiben unverändert gegenüber v2.

| Kommando | Payload | Antwort |
| --- | --- | --- |
| `0x06` Helligkeit v3 | 1 Byte, 0..255 | `0x86`, 1 Byte angewendete Helligkeit |

Der Uno antwortet erst nach der Helligkeitsverarbeitung und einer gegebenenfalls
ausgeführten LED-Ausgabe. Der Pi hält den I/O-Lock bis zur Antwort; in dieser Zeit
beginnt kein weiteres Kommando oder Frame. Anschließend erzwingt der Renderloop
ein vollständiges Bild, um die verlustbehaftete interne NeoPixel-Helligkeitsskalierung
aus den ursprünglichen RGB-Werten zu rekonstruieren.

Während ein Frame empfangen wird, gilt sein LED-Puffer als ungültig. Nur ein komplett
empfangenes Frame mit gültiger Checksumme macht ihn wieder gültig. Helligkeitskommandos
dürfen einen ungültigen Puffer **nicht anzeigen**. Ein solches Kommando setzt weiterhin
die Helligkeit und bestätigt sie; das nächste gültige Vollbild stellt die Ausgabe her.
Das benötigt keinen zweiten 768-Byte-Puffer auf dem Uno.

### Kompatibilität

- **v3 empfohlen:** Frame- und Helligkeitskommandos sind bestätigt; Schutz vor
  sichtbaren Teil-/Fehlerframes bei Helligkeitsänderung.
- **v2 Übergangsbetrieb:** Frame-ACK vorhanden; vor Folgekommandos nach Helligkeit
  wartet der Pi auf abgearbeitete Host-TX-Daten und zusätzlich ca. 27,7 ms
  (LED-Ausgabezeit + 20 ms Reserve). Das ist eine konservative Schutzzeit,
  **keine vom Uno bestätigte Bereitschaft und keine Garantie gegen beliebig
  verzögerte USB-Brücken**. Der alte Sketch hat keinen Ungültig-Puffer-Schutz.
- **v1 oder fehlgeschlagene Protokollprobe:** keine unbestätigten Frames mehr;
  Verbindung bleibt im sichtbaren Fehler-/Reconnect-Zustand. Firmware aktualisieren.
- Ältere Pi-Anwendung kann die v3-Firmware weiterhin über die erhaltenen
  v2-Kommandos bedienen. Für einen sauberen Rollback trotzdem zusammengehörige
  Pi-/Firmwarestände verwenden.

## Lokale Validierung

- **64 lokale Tests erfolgreich** (Python 3.14); zusätzlich erfolgreicher AVR-Build.
- Hardwarefreie Python-Tests: Protokoll, v2/v3-Helligkeit, kurze Writes, statische
  Wiederholung, Reset, Shutdown, Frame-Pacing und Mapping-Neuausgabe.
- ASGI-Konkurrenztest: Während einer blockierten Hardwareoperation bleibt die
  passive Messroute erreichbar. Voller App-Lifespan mit temporärer SQLite-Datenbank
  und expliziter Mock-Ausgabe wird ebenfalls getestet.
- Native C++-Tests kompilieren den **tatsächlichen Sketch** mit Host-Stubs und
  prüfen ACK-Reihenfolge, defekte Frames und Timeout-/Helligkeits-Verhalten.
  Dafür wird `g++` benötigt; ohne Compiler wird dieser Test als übersprungen markiert.
- Echter Uno-Build mit Arduino CLI **1.2.2**, AVR-Core **1.8.6**, Adafruit NeoPixel
  **1.12.3** erfolgreich: 5276 Byte Flash, 270 Byte statische globale Daten.
  Zusätzlich werden die **768 Byte LED-Puffer dynamisch allokiert**; diese sind
  in der 270-Byte-Zeile des Compilers nicht enthalten. Hinzu kommen Stack/Heap-Verwaltung.
- GitHub Actions enthält jetzt auch diesen gepinnten Firmware-Build.

Keine dieser Prüfungen ersetzt den USB-/LED-Test auf dem echten Pi 3 + Uno.
Es wurde nichts auf den Pi kopiert und kein Arduino geflasht.

## Reproduzierbarer Firmware-Build (ohne Flashen)

Mit installierter Arduino CLI 1.2.2:

```bash
arduino-cli core update-index
arduino-cli core install arduino:avr@1.8.6
arduino-cli lib install "Adafruit NeoPixel@1.12.3"
arduino-cli compile --fqbn arduino:avr:uno arduino/PixelDockUnoR3
```

Das erzeugt nur ein Build; es enthält bewusst keinen Upload-Befehl.

## Vor dem nächsten Hardware-Schritt

1. Vorhandene Pi-Konfiguration, Datenbank, Mapping und Assets sichern.
2. Tatsächliche OS-/Python-Version, Uno-Modell und momentanen Firmwarestand erfassen.
3. Baseline bzw. separaten Teststand auf dem Pi vorbereiten und Flashen ausdrücklich
   freigeben. Boot-/Reset-/USB- und Sensor-Einflüsse auf der echten Hardware testen.
4. Danach mit [passiver Messung](tests-und-messungen.md) 30-FPS-Dauerlauf prüfen.

Offen bleiben optische Messung/Logikanalysator, CRC statt XOR, priorisierte
Kommandowarteschlange und Pixel-Art-Assetplayer. Auch Sender-Reconnect kann für
die Arduino-Bootzeit mehrere Sekunden dauern; in dieser Zeit rendert der Pi weiter
und bewahrt nur das neueste wartende Bild auf.
