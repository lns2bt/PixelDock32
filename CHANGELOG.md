# Changelog

Alle nennenswerten Änderungen an PixelDock32 werden in dieser Datei dokumentiert.

## [0.2.0] - 2026-10-14

### Neu

- Pixel-Studio mit GIF-/PNG-Import, Animationseditor, Varianten und Playlist-Verwaltung.
- GIFs vor dem Import oder im Editor per Framezahl oder Zeitbereich kürzen;
  Frames zeitgetreu ausdünnen, Auswahl vorab prüfen und Änderungen rückgängig machen.
- Importvorbereitung für bis zu 4096 Quellframes; fertige Assets bis zu 512 Frames.
- Drei GIF-Wiedergabemodi: maximale Dauer, ein vollständiger Durchlauf und
  Zeitlimit mit anschließendem Loopabschluss; Tempo in der Dauerberechnung berücksichtigt.
- Time-Stage mit 20 Uhransichten, Ereignissen, eigenständiger Zeitplanung,
  Schlafmodus und offline berechneten Sonnen-/Mondzeremonien.
- Bitcoin-Stage mit zehn Stilen, sieben fair rotierenden Infos und Blockzeremonien.
- Wetter-Stage mit vier Stilen für Außen, Innen, Feuchtigkeit und aktuelles Wetter;
  Sonne/Mond/Wolken/Regen/Schnee/Nebel und gedämpfte Gewittermotive.
- Open-Meteo-Wettercode, Tag/Nacht, Niederschlag und Wind aus einer gemeinsamen Abfrage;
  getrennte Aktualität für Außen- und Sensordaten sowie Trends aus echten Messwerten.
- Kompakte mobile Einstellungen, einklappbarer persistenter Header und direkte
  LED-Vorschauen mit ungespeicherten Optionen, ohne Überlagerungsdialog.
- Gemeinsamer Vorschau-Slot mit Ersatz statt Warteschlange und Fortsetzung
  pausierter Vorstellungen ohne Verbrauch regulärer Rotationsplätze.

### Korrigiert

- GIF-Anzeigedauer ist standardmäßig eine echte maximale Dauer statt stiller
  Verlängerung bis zur nächsten Loopgrenze; gilt auch für „Jetzt“.
- Bitcoin- und Wetter-Vorstellungen verwenden eine einheitliche automatische
  Dauerberechnung, ohne zusätzliche Playlist-Mindestdauer.
- Keine erneute alte Info-Beschriftung zwischen den Lesephasen.
- Frische Innenmessungen können veraltete Außendaten nicht mehr als frisch markieren.
- Schlafschutz gilt auch für Vorschauen; simulierte Daten bleiben ausschließlich im Browser.

### Betrieb und Prüfung

- Überarbeiteter Datenweg für etwa 30 FPS, Uno-Firmware v3 und persistente Helligkeit.
- Hardwarefreie API-, Renderer-, Controller-, Daten-, Firmware- und Browser-Tests.
- Getrennte Pi-Installationen mit Sicherung; vorhandene Einstellungen und Assets erhalten.
- Aktuelle Pi-Prüfung: 236 Tests erfolgreich, lokale Prüfung: 237 Tests erfolgreich.
- Hinweis: Innenwerte benötigen gültige DHT-Messungen. Der eingesetzte Sensor meldet
  derzeit Lesefehler; fehlende Werte erscheinen korrekt als `--`. Open-Meteo liefert
  modellbasierte Bedingungen, keine Wetterbeobachtung direkt am Gerät.

## [0.1.0] - 2026-07-09

### Status

- Erste als stabil markierte Arbeitsversion des Projekts.
- Geeignet als Rückkehrpunkt vor den nächsten Feature- und UI-Verbesserungen.

### Enthalten

- FastAPI-Weboberfläche zur Steuerung des 32x8-Pixel-Displays.
- Modulares Rendering mit Uhr, Textbox, Bitmap, Wetter- und BTC-Modulen.
- Debug-, Mapping- und Preview-Werkzeuge für Panel-Setup und Fehlersuche.
- USB-Serial-Transport zum Arduino UNO R3 inklusive Frame-ACK-Unterstützung.
- Raspberry-Pi-Systemd-Services, Healthcheck und Autostart-Hilfen.
- Projektdokumentation für Setup, Hardware-Mapping, API, Module und Roadmap.

### Hinweis

Diese Version ist bewusst als sichtbarer GitHub-Snapshot gedacht. Für eine dauerhafte Markierung sollte nach dem Merge zusätzlich ein Git-Tag `v0.1.0` auf diesen Stand gesetzt werden.
