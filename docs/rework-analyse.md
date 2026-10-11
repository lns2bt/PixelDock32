# Rework: Bestandsanalyse und Entscheidungsgrundlage

Stand: 12. Oktober 2026. **Noch kein Umbau der Anwendung oder Firmware.**

## Arbeitsbereich und Rückkehrpunkt

- Repository: https://github.com/lns2bt/PixelDock32
- Lokale Arbeitskopie: `/home/bit/Work/PixelDock32`
- Separater GitHub-Zweig: `rework/smooth-led-pipeline`
- Unveränderter Ausgangscommit: `97a27ec65b662979aa89c619341c3b2ad154f9f2`
- `main` wurde nicht verändert. Der Ausgangscommit bleibt die exakte Referenz,
  auch wenn `main` später weiterentwickelt wird.

Ein Software-Rollback muss später **Pi-Anwendung und Arduino-Firmware gemeinsam**
berücksichtigen. Git sichert weder die auf dem Uno geflashte Firmware noch lokale
`.env`, Datenbank, Mapping-Zustand oder zusätzlich hochgeladene Bilddateien.
Vor einem Hardware-Test müssen diese separat gesichert werden.

## 1. Bestehende Architektur

```text
Browser im Heimnetz
  → FastAPI / REST / statisches HTML und JavaScript
  → SQLite-Modulkonfiguration + Cache für Wetter/BTC/DHT
  → asyncio-Renderloop: standardmäßig 20 FPS, 32 × 8 Pixel
  → logisches Bild + Farbmatrix → vorberechnetes LED-Mapping
  → RGB-Bytepuffer → separater Serial-Senderthread
  → USB-Seriell, 1.000.000 Baud, PD-Protokoll v2
  → Uno: Empfangsparser, Helligkeitsskalierung, GRB-Puffer
  → Adafruit_NeoPixel.show(), D6
  → 256 WS2812B-LEDs in einer seriellen Kette
```

Der Browser steuert die Inhalte; er liefert aktuell nicht jeden Animationsframe.
Die Animationen entstehen auf dem Pi. Der Uno R3 ist dabei kein nativer
USB-Framebuffer-Controller: Eine USB/UART-Brücke verbindet den Pi mit dem AVR.
Die genaue Brücke (Original-Uno/Clone) muss an der Hardware bestätigt werden.

### Gute Grundlagen, die erhalten werden sollten

- Binäre Vollbilder statt JSON/Text über die serielle Verbindung.
- Bereits 1 Mbaud, Sequenznummern und Bestätigung nach der LED-Ausgabe.
- Separater Senderthread mit nur einem wartenden Frame: Ein neuer Frame ersetzt
  einen alten wartenden Frame, statt eine wachsende Latenz-Warteschlange zu erzeugen.
- Unveränderte Bilder werden nicht erneut übertragen.
- Mapping-Lookup ist bereits vorberechnet; Bitmap-Dateien werden gecacht.
- HTTP-Poller sind asynchron; reguläre DHT-Messungen laufen über `asyncio.to_thread`.
- Debug-Zähler für Transport, Fehler und Rendering sind vorhanden.
- Sieben prozedurale Animationen, Text, Uhr, Wetter, BTC und Bitmap-Anzeige bestehen.

## 2. Zeitbudget: Wo liegt die Grenze?

Für ein v2-RGB-Vollbild:

| Bestandteil | Umfang / theoretische Zeit |
| --- | --- |
| Pixeldaten | 256 × 3 = 768 Byte |
| Sequenz + Header + XOR | 8 Byte |
| Pi → Uno, 8N1 bei 1 Mbaud | 776 × 10 / 1.000.000 = **7,76 ms** |
| WS2812B-Daten bei 800 kbit/s | 256 × 24 / 800.000 = **7,68 ms** |
| Uno → Pi: Frame-ACK | 8 Byte = **0,08 ms** UART-Leitungszeit |
| Summe | **15,52 ms**, ohne USB-/OS-/Parser-/Latch-Zusatzkosten |

Das entspricht einer idealisierten Obergrenze von etwa **64,4 Vollbildern/s**
für das bestehende Stop-and-wait-Verfahren. Das ist **kein gemessener Durchsatz**.
60 FPS haben nur 16,67 ms Zeit pro Bild und damit sehr wenig Reserve; 30 FPS
(33,33 ms) sind zunächst das vernünftigere Mess- und Stabilitätsziel.

Auf AVR sperrt NeoPixel-Ausgabe üblicherweise Interrupts während der Datenphase.
Der Uno kann dann den normalen interruptgetriebenen UART-Empfang nicht bedienen.
**Nicht einfach das ACK entfernen oder Frames blind pipelinen:** Das riskiert
Empfangsverluste während `show()`. Ein größerer Software-RX-Puffer allein löst
diese Interruptsperre nicht. Auch AVR-Zeitmessung über `millis()` kann dadurch
beeinflusst werden; Firmware-Zeitwerte sind nicht automatisch Referenzmessungen.

### Denkbare Transportwege, noch keine Entscheidung

1. **Uno behalten, RGB v2 zunächst stabilisieren:** geringstes Hardware-Risiko;
   gleichmäßige 30 FPS zuerst nachweisen, danach höhere Raten ausmessen.
2. **Optionales palettenbasiertes Vollbild:** besonders passend für Retro-Pixel-Art.
   Beispiel mit 16 Farben: 48 Byte Palette + 128 Byte 4-bit-Indizes + 8 Byte
   Protokollrahmen ergeben ungefähr 184 Byte bzw. 1,84 ms Übertragungszeit.
   Die LED-Ausgabe bleibt 7,68 ms; Decoder und Protokoll brauchen eigene Tests.
   RGB-Fallback für Verläufe behalten, nicht ungefragt Farben reduzieren.
3. **Moderner LED-Controller, z. B. RP2040 mit PIO oder ESP32 mit RMT/DMA:**
   bessere Möglichkeiten für nebenläufigen Empfang und zeitgesteuerte Ausgabe.
   USB-/Serial-Implementierung und konkrete Board-Variante separat bewerten.
4. **Direkte Pi-Ausgabe:** im Projekt vorhanden, aber abhängig von Pi-Modell,
   Treibern, GPIO und Pegelanpassung. Kein ungeprüfter Standardwechsel.

Delta-Frames/RLE erst nach Messung erwägen: Sie können bei einfachen Sprites helfen,
machen aber Fehlerbehandlung und Zustandsabgleich schwieriger. Vollbilder bleiben
bei 256 Pixeln eine einfache, robuste Basis. Höhere Baudrate allein beseitigt weder
die LED-Ausgabezeit noch schlechtes Frame-Pacing.

## 3. Konkrete Probleme und Risiken

### P0: Gleichmäßigkeit und Betriebssicherheit

- **Blockierende Debug-Aufrufe im asyncio-Webserver.** `app/api/debug.py` ruft
  serielle Diagnose, Ping, DHT-Einzelmessung und GPIO-Tests synchron aus
  `async def`-Routen auf. Serial-Diagnose wartet auf denselben Lock wie der Sender;
  GPIO-Tests enthalten Sleeps, DHT kann lange wiederholen. Währenddessen kann
  auch der Renderloop stillstehen. Status-Polling kann dabei echte Serial-Abfragen
  auslösen (`LEDDriver.get_debug_snapshot`).
- **Helligkeitskommando ohne Ausgabebestätigung.** Die Firmware macht auch für
  Helligkeit `strip.show()`, aber der Pi wartet nicht auf dessen Abschluss.
  Ein direkt anschließendes Frame oder Diagnosekommando kann in die
  interruptgesperrte Ausgabe geraten. Ein einzelner Kommunikations-Owner mit
  expliziter Ready-/ACK-Regel für alle auslösenden Kommandos wäre sauberer.
- **Automatischer Rückfall auf Mock-Ausgabe.** Bei Hardware-Initialisierungsfehlern
  bleibt der Webserver mit virtueller Anzeige aktiv; ein später angeschlossener
  Uno wird aus diesem Mock-Zustand nicht automatisch aktiviert. Für Entwicklung
  hilfreich, für Produktion besser ein klarer Fehler-/Reconnect-Zustand.
- **Kein sauberer Transport-Shutdown.** Der Sender hat ein Stop-Event, aber keine
  aufgerufene Close-/Join-Methode. Der FastAPI-Lifespan stoppt nur Display und Poller.

### P1: Timing, Protokoll und korrekte Anzeige

- Standard sind **20 FPS**, nicht 30/60. Renderloop-Sleep korrigiert Arbeitszeit,
  verwendet aber keine fortlaufenden absoluten Deadlines; Scheduler-Verzögerungen
  können sich addieren. Animationen sollten eine gemeinsame monotone Zeitbasis
  bekommen. Die Animationsklasse nutzt sie schon, andere Pfade nutzen `time.time()`.
- **„actual_fps“ zählt Renderloop-Durchläufe über die gesamte Laufzeit**, nicht die
  tatsächlich auf dem Display bestätigten Bilder. `last_led_write_ms` misst beim
  Serial-Backend im Wesentlichen Enqueue-Arbeit, nicht die komplette Übertragung.
  Es fehlen aktuelle Fensterwerte und Perzentile für angezeigte Frame-Abstände.
- **Enqueue ist nicht Anzeige.** Das zuletzt erzeugte Bild wird im Renderloop
  sofort als letzter Stand gespeichert. Schlägt seine Übertragung dauerhaft fehl,
  kann ein statisches Bild danach als „unverändert“ übersprungen werden, solange
  kein erfolgreicher Reconnect die Resync-Flag setzt. Soll-/Ist-/bestätigten Zustand
  getrennt führen und nach Fehlern einen Wiederabgleich garantieren.
- **XOR ist schwache Fehlererkennung.** Bestimmte Mehrbitfehler bleiben unentdeckt.
  CRC und Resynchronisierung bei Teilpaketen verdienen Tests. Der Empfang schreibt
  bereits vor Checksum-Prüfung in den NeoPixel-Puffer; ein ungültiges Bild wird
  zunächst nicht ausgegeben, kann aber über ein späteres Helligkeitskommando
  sichtbar werden. Für Delta-Frames wäre dieser Ansatz besonders problematisch.
- **Statische Mapping-Änderungen erzwingen kein neues Bild**, solange logisches
  Frame und Farben gleich bleiben. Mapping-Revision in die Ausgabeentscheidung
  einbeziehen.
- **Übergänge können Animationen stören.** Bei `transition_on_content_change`
  können wechselnde Animations-/Scrollframes neue Übergänge anstoßen. Das
  Animationsmodul hat sinnvollerweise `transition_ms=0` als Default; Modulwechsel
  und laufende Animation sollten trotzdem unabhängig behandelt werden.

### P2: Wartbarkeit, Pixel-Art und Umgebung

- Viele 32×8-Konstanten trotz konfigurierbarer Geometrie; Pi-LED-Anzahl kann vom
  fest auf 256 eingestellten Uno abweichen. Geometrie/Protokollkapazität validieren.
- Parallel geführtes Binärbild und Farbmatrix sowie Dict-/Listen-Konvertierungen
  pro Bild. Ein einheitliches RGB-Framebuffer-Format könnte vereinfachen; bei
  256 Pixeln erst messen, nicht voreilig Mikrooptimierung priorisieren.
- Bitmap-Unterstützung ist statisch mit vertikalem Scrollen. GIF/APNG/Spritesheets,
  Frame-Dauern und pixelgenaue Skalierung fehlen. Retro-Ästhetik ist nicht allein
  eine FPS-Frage: bewusstes Sprite-Timing und ganzzahlige Positionen sind wichtig.
- Browser-Vorschau pollt jede Sekunde und zeigt den erzeugten, nicht unbedingt
  den bestätigten Frame. Sie eignet sich aktuell nicht zur Beurteilung der
  tatsächlichen Display-Flüssigkeit.
- Hardwarepakete stehen verpflichtend in `requirements.txt`; kein getrenntes
  Desktop-/Pi-/Test-Setup. Firmware-Core und NeoPixel-Version sind nicht gepinnt.
- Keine Test-Suite/CI im ausgecheckten Stand; es gibt einen Glyphen-Regressionscheck.
- Konfigurationsdefaults enthalten bekannte Login-/JWT-Werte. Vor Produktivbetrieb
  explizite sichere Werte verlangen; Abhängigkeiten später separat prüfen.
- `LED_TRANSPORT=auto` bevorzugt bei importierbarem `rpi_ws281x` Pi-GPIO, nicht Uno,
  obwohl USB laut README der Standardweg sein soll. Hardwarewahl explizit machen.

## 4. Durchgeführte lokale Checks

Ohne Pi/Uno-Verbindung und ohne Installation von Hardwarepaketen:

- Python-AST-Syntaxprüfung: **34 Dateien erfolgreich**, Python 3.14.7.
- `python3 scripts_verify_glyphs.py`: **glyph-regression-ok**.
- Animations-Smokecheck: alle 7 Presets erzeugen 8×32 Bilder mit gültigen
  RGB-Kanälen; zusätzlich 140 Preset-/Palette-/Mirror-Kombinationen aufgerufen.
- Pro Preset 20 Warmups + 200 lokale Render-Messungen:

| Preset | Median (ms) | p95 (ms) |
| --- | ---: | ---: |
| bit_invaders | 0,151 | 0,282 |
| lava_lamp | 1,482 | 3,440 |
| matrix_rain | 0,201 | 0,580 |
| neon_equalizer | 0,547 | 1,019 |
| pixel_snake | 0,154 | 0,363 |
| psychedelic_plasma | 1,152 | 1,767 |
| retro_rainbow_tunnel | 0,845 | 1,366 |

**Diese Werte stammen vom lokalen Entwicklungsrechner, nicht vom Raspberry Pi.**
Sie messen nur `AnimationsModule.render`, nicht Datenbank, Mapping, Transport oder
LED-Ausgabe. Kein vollständiger Webserver-/Firmware-/Hardwaretest durchgeführt.
Die fehlenden Python-Web-/Serial-Abhängigkeiten wurden für diese Analyse nicht
installiert. Keine Aussage über reale FPS oder optische Signalqualität möglich.

## 5. Vorschlag für das gemeinsam zu beschließende Rework

1. **Baseline und reproduzierbare Tests:** Protokoll-, Mapping-, Queue-, Shutdown-
   und Fehlerfalltests; simulierter Uno ohne Hardware; reproduzierbare Firmware-Builds.
   Auf dem echten Pi Frame-Abstände, ACK-Zeiten, Fehler und ersetzte Frames messen.
2. **Bestehenden RGB-Weg stabilisieren:** Hardware-Owner, nonblocking API,
   bestätigte Kommandos, monotone Deadlines, Shutdown, Reconnect und Resync.
   Gleichmäßige 30 FPS als erstes vorgeschlagenes Abnahmeziel.
3. **Transportentscheidung nach Messung:** Uno + RGB, optional Palettenframes oder
   moderner Controller; 60 FPS erst als Ziel zusagen, wenn genug Reserve besteht.
4. **Pixel-Art-Pipeline:** Sprite-/Animationsassets, zeitbasierter Player,
   Nearest-Neighbor/Crop, definierte Paletten, saubere Modulwechsel und Preview.
5. **Aufräumen und Betrieb:** kleinere klar getrennte Komponenten, Entwicklungs-
   und Hardwareabhängigkeiten, CI, sichere Konfiguration und Upgrade/Rollback-Doku.

Abnahme nicht allein über durchschnittliche FPS: vorgeschlagene Messreihe mit
vollflächiger Animation, statischem Bild, offenen Debug-Seiten, API-Last und
USB-Ab-/Anstecken. Mindestens 10 Minuten Dauerlauf; Frame-Abstände p50/p95/p99,
lange Aussetzer, ACK-/Checksum-Fehler und Recovery dokumentieren. Konkrete Grenzwerte
für Jitter und Wiederverbindung erst nach Hardware-Baseline gemeinsam festlegen.

## 6. Noch gemeinsam zu klären

Inzwischen bestätigt: Raspberry Pi 3 mit 1 GB RAM, Raspberry Pi OS ohne Desktop,
32×8 WS2812B-Pixel, 30 FPS als Ziel, Uno zunächst behalten. Text, Sprites/GIFs
und prozedurale Animationen sollen unterstützt werden. SSH-Zugriff ist vorhanden.
Phase 1 (lokale Tests und Messgrundlage) wurde freigegeben; Umsetzung und Grenzen
stehen unter [Tests und Messungen](tests-und-messungen.md).
Die folgende ursprüngliche Fragenliste bleibt zur Nachvollziehbarkeit erhalten.

- Welches Raspberry-Pi-Modell, OS und Python-Version laufen tatsächlich?
- Original Uno R3 oder Clone, und welche USB/UART-Brücke?
- Bleibt die Anzeige bei vier WS2812B-8×8-Panels / 32×8 Pixeln?
- Sind 30 FPS genug, oder sollen 60 FPS unter Last das feste Ziel sein?
- Muss der Uno bleiben, oder wäre ein günstiger Controllerwechsel möglich?
- Gewünschte Inhalte: eigene Sprites, GIFs, Gameszenen, Laufschrift, Datenmodule?
- Welche Ruckler/Fehler treten derzeit auf, mit welchen `.env`-Werten?
- Wie können später Pi-Zugriff und abgesicherte Hardwaretests erfolgen?
