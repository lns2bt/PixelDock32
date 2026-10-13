# Time-Stage – Szenenatelier und eigenständige Uhr-Regie

## Umfang und Grenze dieses Schritts

Schritt 1 lieferte 20 normale Uhransichten und 10 besondere Ereignisanimationen als
reine, zustandslose 32×8-Renderer. Schritt 2 ergänzt eigenständige Uhr-Regie,
Migration, Schlafmodus, Einstellungen und lokale Himmelsberechnung. Die Inhalte
anderer Module bleiben unverändert.

Die Bibliothek liegt in `app/services/time_stage/`. `core.py` definiert die gemeinsame
Canvas-/Metadaten-Schnittstelle; sechs unabhängige Stilgruppen liefern die Szenen.
`render_scene(key, now, elapsed)` liefert den üblichen `ModulePayload` ohne Datei-,
Datenbank-, Netzwerk- oder Hardwarezugriff. Die Renderzeit wird begrenzt und geprüft;
Pixel werden auf das Panel zugeschnitten und RGB-Werte auf 0–255 begrenzt.

Normale Sekunden-Effekte beziehen sich auf `now.second` und Mikrosekunden, nicht
auf die seit dem Playlist-Auftritt vergangene Zeit. `elapsed` steuert zusätzliche
Bewegung und Übergänge. Ereignisse sind endliche, 6–10 Sekunden lange Choreografien;
die Schlussphase zeigt die **aktuelle** Uhrzeit. Event-Metadaten schlagen Kategorien
vor, lösen aber nichts automatisch aus.

## Vorschauen erzeugen

```sh
.venv/bin/python scripts/preview-time-stage.py --output /tmp/opencode/time-stage-preview-v1
```

Die Ausgabe enthält eine responsive statische HTML-Galerie, GIF-/PNG-Vorschauen,
`catalog.json` und eine Vergleichstafel `contact-sheet.png`. Normale Szenen zeigen
eine echte Minute im 6×-Zeitraffer; Ereignisse laufen in Echtzeit. Alle Dateien werden
offline generiert – der Browser spielt vorberechnete Bilder ab; im LED-Renderpfad
findet keine GIF-Dekodierung statt. Die Galerie verändert weder Playlist noch LEDs und respektiert
`prefers-reduced-motion`. Originaldateien aus Downloads werden nicht veröffentlicht.

Vorschauen simulieren logische RGB-Pixel, keine Kameraaufnahme. Besonders bei sehr
niedriger Helligkeit ist eine spätere Prüfung auf der tatsächlichen Anzeige nötig.

## Implementierter Schritt 2

- Eigenständiger Bereich **Time-Stage**, außerhalb der Modul-Playlist.
- Uhr nach N regulären Playlist-Einträgen und/oder nach X Sekunden anfordern;
  laufende GIF-Loops/Lauftexte dürfen enden. Die Zeitgrenze ist keine harte Unterbrechung.
- Genau eine normale Szene pro Auftritt; auswählbare Reihenfolge, Zufall und Gewichtung.
- Besondere Ereignisse zu `:00`, `:15`, `:30`, `:45`, separat aktivierbar. Nach einer
  Inhaltsgrenze einmal ausführen und ggf. normale Uhr-Einblendung ersetzen; keine
  veralteten Ereignisschlangen, stets die aktuelle Uhrzeit darstellen.
- Schlafzeit standardmäßig 02:00–08:00: ausschließlich statische rot-orange HH:MM,
  ohne Sekunden/Blinken/Übergänge, eigene Helligkeit standardmäßig 1.
- Globaler Schlafschalter: Automatik / Schlaf erzwingen / Wach erzwingen. Manuelle
  Ausnahme endet beim nächsten Zeitplan-Umschaltpunkt. Tageshelligkeit bleibt erhalten.
- Eigene mobile Einstellungsseite und genaue Zeitfelder zusätzlich zur 24h-Zeitleiste.
- Vor Migration Daten/Einstellungen sichern; andere Modulinhalte nicht verändern.

### Bedienung

`/time-stage` ist eine eigene mobile Seite mit gemeinsamen Live-Header. Das Mondsymbol
im Header schaltet Schlafen/Wach bis zum nächsten Planwechsel; auf der Seite gibt es
zusätzlich Automatik und „2h schlafen“. Die tägliche Schlafzeit ist mit Zeitfeldern
und zwei präzisen 24h-Reglern einstellbar. Der Zeitplan wird erst mit Speichern geändert.

Reguläre Playlist-Slots zählen für die N-Einträge-Regel; Shuffle, Prioritäten und
„Jetzt“ nicht. Ein Ereignis erfüllt zugleich die Uhr-Anforderung. Sehr kurze Intervalle
verdrängen nicht dauerhaft die Playlist. Ohne Playlist läuft die aktivierte Uhr durch.
0 deaktiviert jeweils die Eintrags-/Zeitregel. Zeitlimits sind **weich**; volle GIF-
Loops, Lauftexte und das römische Laufband dürfen fertiglaufen.

Profile: Alle Stile, Retro, Ruhig, Favoriten oder eigene Auswahl; bis zu acht benannte
Szenenprofile speicherbar. Gewichte gelten bei Zufallsauswahl, unmittelbare Wiederholungen
werden vermieden. Bewegung, optionaler Farbton und Minutenwechsel-Effekt sind einstellbar.
Die Browser-Vorschau erlaubt frei gewählte Uhrzeiten, Echtzeit/Zeitraffer und einen
separaten, bestätigungspflichtigen Knopf für echte LED-Vorschauen. Browser-Vorschauen
sind off-thread und verändern keine Playlist oder Hardware; Himmelsdaten für simulierte
Zeiten werden separat und begrenzt gecacht.

### Sonnen-/Monduhr

PyEphem 4.2.1 berechnet offline lokale Sonnen-/Mondaufgänge und -untergänge,
bürgerliche Dämmerung, Goldene-Stunde-Fenster, Sonnenhöchststand, Mondbeleuchtung,
Mondphase, nächste Voll-/Neumonde sowie Sonnenwenden/Tagundnachtgleichen.
Wetterstandort ist Standard; eigene Koordinaten und eine eigene Zeitzone sind möglich.
Die Berechnung läuft off-thread einmal pro Minute beziehungsweise nach Standortwechsel.

Vier primäre Himmelszeremonien sind standardmäßig aktiv, je 45 Sekunden (30–60
einstellbar). Zuerst eine Landschaftsgeschichte, danach auswählbare Zahlentafeln:
Tageslänge/Änderung, Dämmerung, nächster Auf-/Untergang, Phase/Beleuchtung und nächster
Vollmond. Goldene Stunde, Sonnenhöchststand, Voll-/Neumond, Sonnenwende und Äquinoktium
sind zusätzliche, standardmäßig deaktivierte Ereignisse. Fehlende Ereignisse in
Polargebieten oder an einzelnen Tagen bleiben explizit unbekannt; nichts wird erfunden.

Höhenangaben beziehen sich auf den rechnerischen Horizont bei Meereshöhe mit
Standard-Refraktion, nicht auf Berge/Gebäude/Wetter. Die Mondscheibe ist eine stilisierte
Phasenzeichnung, keine Ansicht mit standortabhängigem parallaktischem Winkel.
„Mond heute über dem Horizont“ summiert sichtbare Zeit im lokalen Kalendertag.
Nachtlänge meint den heutigen Sonnenuntergang bis zum folgenden Sonnenaufgang;
bei fehlenden Horizontwechseln wird der dunkle Anteil des lokalen Tages verwendet.

### Sicherheit, Migration und Grenzen

- Schema-Version 1 in `time_stage_preferences`; unbekannte Versionen werden abgewiesen.
- Legacy-Uhrzeilen bleiben archiviert und deaktiviert, statt gelöscht zu werden.
  Dauer, Zeitzone und Prioritätsintervall der ersten aktiven Uhr werden übernommen.
  Alte Szenen werden zuerst auf passende neue Szenen abgebildet; alle 20 sind verfügbar
  und anfänglich aktiviert. Alte Farben bleiben im Archiv; neue Kunststile nutzen ihre
  eigenen Paletten, bis ausdrücklich ein gemeinsamer Farbton gewählt wird.
- Andere Modulzeilen werden bei Migration nicht verändert. Archivierte Uhren erscheinen
  nicht mehr in der Playlist; neue Uhren werden nicht als Playlist-Modul angelegt.
- Helligkeit der Nacht ist unabhängig von der gespeicherten Tageshelligkeit. Tagesänderungen
  während der Nacht werden beim Aufwachen wirksam. Auch normale „Jetzt“-Wiedergaben und
  alte Diagnose-Overrides können den Schlafmodus nicht unbemerkt übersteuern.
- Manuelle Schlaf-Ausnahmen sind mit Ablaufzeit persistiert; keine verpassten Ereignisse
  nach Neustarts, großen Zeitsprüngen oder Aufwachen. Wiederholte lokale Stunden bei
  Sommerzeit-Rückstellung werden nicht doppelt gefeiert. Nicht existierende Schlafzeiten
  im Frühjahr werden um die DST-Lücke nach vorn verschoben.
- Export/Import enthält nur Time-Stage-Einstellungen (Standort kann persönliche Information
  sein), keine Zugangsdaten. Exporte setzen manuelle Schlaf-Ausnahmen auf Automatik zurück.
- Bei fehlerhaften oder leeren Profilen fällt die Anzeige auf eine lesbare Uhr zurück.
  Status meldet Render-/Astronomiefehler und die ungefähr nächste Uhr-Anforderung.
- Keine Gewähr für dauerhaft perfekt konstante 30 FPS; lokale/Pi-Tests ersetzen keine
  spätere Sichtprüfung und Stabilitätsprüfung. Firmware v3 bleibt unverändert.

## Versionierung

Der vorherige GIF-Import-Fix ist vom Benutzer auf dem Pi bestätigt. Dieser und die
Time-Stage-Erweiterung bleiben zunächst lokal; kein GitHub-Push ohne erneute Freigabe.
Nach einem größeren Schritt wird ein separater Pi-Stand mit Sicherung erstellt.
