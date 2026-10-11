# Phase 1: lokale Tests und passive Transportmessung

> Dieser Text dokumentiert den ursprünglichen Phase-1-Stand. Inzwischen ist
> [Phase 2](rework-phase2.md) umgesetzt: Standard 30 FPS, Firmware v3,
> Produktions-Shutdown und verpflichtendes Frame-ACK. Bestehende `.env`-Werte
> bleiben wirksam. Die unten beschriebenen Messwerkzeuge bleiben gültig.

## Vereinbartes Ziel und aktueller Umfang

- Raspberry Pi 3, 1 GB RAM, Raspberry Pi OS (Debian-basiert, ohne Desktop).
- Arduino Uno bleibt zunächst erhalten; 256 WS2812B, 32×8 Pixel.
- Ziel nach Stabilisierung: gleichmäßige **30 FPS**.
- Inhalte später: Text, Sprites/GIFs und prozedurale Animationen.

Phase 1 ergänzt Tests und hostseitige Messwerte. Baudrate, Standard-FPS,
Protokoll und Firmware werden **nicht** geändert. Es findet keine Installation,
kein Flashen und kein Zugriff auf den Pi statt.

## Lokale Tests ohne Pi/Uno

Vom Repository-Hauptverzeichnis:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m unittest discover -s tests -v
```

Die Testabhängigkeiten enthalten keine Pi-/GPIO-Pakete. Python 3.11 oder neuer
verwenden. GitHub Actions prüft Python 3.11 und 3.13; lokal wurde zusätzlich
Python 3.14 verwendet. Die bestehenden Web-Abhängigkeiten können dort
Deprecation-Warnungen ausgeben; ihre Aktualisierung gehört nicht zu Phase 1.

Abgedeckt:

- Literal-Protokollvektor, v2-Erkennung, RGB-Frame, Sequenzüberlauf und Ping.
- Fehlendes ACK, falsche Sequenz, defekte Checksumme, Retry und Reconnect.
- v1-Senden zählt nicht als bestätigte Anzeige.
- Wartendes Frame wird ersetzt; Enqueue kopiert die Bilddaten.
- Senderthread liefert Frames; Test-Harness beendet ihn anschließend.
- Mapping-Bijektion, Panelrotationen/-reihenfolge, persistente Pixelkorrektur.
- Glyphen, Bitmap-Cache, Pfadbegrenzung und 140 Animationskombinationen.
- Messfenster, Perzentile, Idle-Verhalten und Speicherbegrenzung.
- Authentifizierte passive API ohne Hardware-Abfrage; Collector-Fehlerfälle.

`tests/fake_uno.py` emuliert Pakete und Antworten. **Er emuliert weder AVR-Timing
noch Interruptsperren, USB-Latenz oder elektrische Signale.** Erfolgreiche Tests
beweisen deshalb keine 30 FPS auf echter Hardware. Der Produktions-Shutdown
ist weiterhin eine bekannte Phase-2-Aufgabe; das Test-Cleanup ist keine Lösung dafür.

## Passive API

`GET /api/debug/led/metrics` benötigt denselben Bearer-Token wie die übrigen
geschützten APIs. Die Route sendet keine Kommandos an den Uno und nimmt nicht
den seriellen I/O-Lock. Sie liest nur bereits gespeicherte Zähler und Messwerte.
Der kleine Messpuffer ist auf 2048 Bestätigungen begrenzt.

Im Serial-Ergebnis:

- `frame_ack_enabled`: nur bei aktivem v2-ACK sind bestätigte Frames messbar.
- `counters`: Enqueue, erfolgreiche Sends, ersetzte Frames, ACK-/Write-Fehler,
  Retry-/Reconnect-Zähler und Senderfehler. Dies sind Laufzeit-Gesamtzähler.
  Unterschiedliche Zähler können sich während eines Snapshots weiterbewegen;
  sie sind keine atomare Transaktionsbilanz.
- `confirmations.confirmed_frames_total`: erfolgreich bestätigte Frames seit Start.
- `confirmed_fps_window`: Bestätigungen pro Sekunde im letzten 30-s-Fenster,
  anfangs bezogen auf die kürzere Laufzeit. Bei Pufferüberlauf `null`, nicht eine
  irreführend zu niedrige FPS-Zahl.
- `ack_interval`: p50/p95/p99/max der hostseitigen ACK-Abstände. Ein Abstand zählt
  in das Fenster, wenn seine abschließende Bestätigung darin liegt.
- `successful_attempt_roundtrip`: Dauer des erfolgreichen Sende-/ACK-Versuchs;
  vorherige Retry-/Reconnect-Zeiten sind darin nicht enthalten. Aussetzer erscheinen
  dagegen in den ACK-Abständen bzw. im Alter der letzten Bestätigung.
- `queue_wait`: Wartezeit des Frames vor dem Sender, nicht gesamte Bildlatenz.
- `last_confirmation_age_ms`: Zeit seit letzter Bestätigung, auch bei Stillstand.

**Interpretation:** Der Uno bestätigt nach `strip.show()`. Die Messung beschreibt
den Empfang dieser Bestätigung auf dem Pi, nicht den exakten optischen Zeitpunkt.
USB-/OS-Latenz beeinflusst sie. Statische Bilder werden absichtlich nicht ständig
gesendet; niedrige bestätigte FPS und lange ACK-Abstände sind dort normal.
Keine Bestätigungen bei Mock-/GPIO-Backend bzw. v1 sind kein Beweis für ein defektes
Display. Das Ergebnis nennt deshalb das tatsächlich aktive Backend.

## Spätere Messung auf dem Pi per SSH

Erst nach separater Freigabe und Sicherung von `.env`, Datenbank, Mapping und
Assets den Rework-Stand auf dem Pi verwenden. Der folgende Collector setzt voraus,
dass dort bereits der Server mit der neuen Messroute läuft. Ein unveränderter alter
Server antwortet auf die Route mit HTTP 404.

Für eine vergleichbare Baseline zunächst die vorhandenen Einstellungen behalten
(Standard: 20 FPS). 30 FPS erst in der Stabilisierung separat testen und in jedem
Messlauf die tatsächlich verwendete Konfiguration notieren.

1. Im Browser anmelden und den Zugangstoken aus der Login-Antwort verwenden.
   Token nicht in Chat, Git oder Messdateien kopieren.
2. SSH auf den Pi; im Repository einen privaten Ergebnisordner erstellen:

```bash
umask 077
mkdir -p measurements
read -rsp 'PixelDock access token: ' PIXELDOCK_TOKEN
echo
export PIXELDOCK_TOKEN
python3 scripts/measure-transport.py \
  --url http://127.0.0.1:8000 \
  --duration 600 \
  --interval 1 \
  --output measurements/animation-baseline.jsonl
unset PIXELDOCK_TOKEN
```

Der Collector braucht nur Python-Standardbibliotheken. Er liest ausschließlich
die passive Route und **ändert weder Inhalte noch Helligkeit oder FPS**.
Er überschreibt keine vorhandene Datei, folgt keinen HTTP-Weiterleitungen und
speichert den Token nicht. Bei Abbruch bleiben die bisher geschriebenen Samples
erhalten. Netzwerk-/HTTP-Fehler werden protokolliert und führen zu Exit-Code 1;
die Ausgabe enthält rollende Statistiken, keinen automatisch aggregierten
10-Minuten-p99-Wert. Perzentile verschiedener Fenster darf man nicht mitteln.

## Messmatrix für die spätere Hardware-Abnahme

Jeden Lauf als eigene Datei und mit Pi-/OS-/Python-Version, Firmwarestand,
Transport, Baudrate, Ziel-FPS und gewähltem Inhalt dokumentieren:

| Lauf | Zweck |
| --- | --- |
| Vollflächige Animation, 10 Minuten | Durchsatz, Frame-Pacing, Fehler |
| Gleiche Animation, Debug-Seite offen | Einfluss bestehender aktiver Debug-Abfragen |
| Gleiche Animation, zusätzliche API-Bedienung | Web-/Rendering-Konkurrenz |
| Statisches Bild | unveränderte Frames werden übersprungen |
| USB abziehen/anstecken, separat freigegeben | Recovery und Wiederabgleich |

Zunächst Baseline erfassen, dann nach Phase 2 erneut unter denselben Bedingungen
messen. 30 FPS entsprechen 33,33 ms pro Bild. Konkrete Jitter-/Recovery-Grenzwerte
nach der Baseline festlegen; 30 FPS sind in Phase 1 noch nicht nachgewiesen.
