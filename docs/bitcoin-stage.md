# Bitcoin-Stage

Die neue Darstellung nutzt das bestehende Bitcoin-Playlist-Modul, keine zweite
unabhängige Playlist. Andere Module, Time-Stage und gespeicherte Inhalte bleiben
unverändert. Einstellungen und echte/browserbasierte Vorschauen: `/bitcoin`.

## Gleichberechtigte Rotation

Sieben auswählbare Infos: EUR-Preis, Blockhöhe, Sats/€, Alter des letzten Blocks,
Gebühren in sat/vB, Restblöcke bis zum nächsten Halving, 24h-Preisänderung.
Standard: alle aktiv, maximal **zwei Infos pro Vorstellung**, faire geordnete Rotation.
Keine Doppelungen innerhalb einer Vorstellung. Eine kleine Auswahl wird nicht
künstlich aufgefüllt. Bei Zufall leert sich erst ein gemischter Beutel, bevor eine
neue Runde beginnt; höchstens eine Info kann im Durchlauf vorne liegen.

Jedes Modul hat seinen eigenen Rotationszustand im Speicher. Neustarts beginnen
wieder mit der konfigurierten Reihenfolge; Browser- und explizite LED-Vorschauen
verbrauchen keine normalen Rotationsplätze. Konfigurationsänderungen gelten ab
dem nächsten Besuch; ein laufender Besuch behält seine Werte und Einstellungen.

Eine Szene pro Vorstellung, unabhängige Szenenauswahl geordnet oder zufällig ohne
direkte Wiederholung bei mehreren Stilen. Zehn Motive: Schmiede, Blockchain-Zug,
Mining-Schacht, Nonce-Suche, Orbit, Transaktionsregen, Terminal, mechanischer Zähler,
Tetris, Goldader. Alle Infos funktionieren in jedem Stil. Kunstmotive sind keine
echten Mining-/Mempoolmessungen. Ruhige/normal/lebhaft einstellbar.

Kurzer Einstieg, pro Info Beschriftung → Motiv → Übergang → ruhige Lesephase →
Ausklang. Standard-Lesezeit vier Sekunden (2–15 einstellbar), gesamte Vorstellung
mit zwei Infos ca. 17,4 Sekunden. **Automatische Gesamtdauer** statt einer zweiten
Playlist-Mindestdauer: Infoanzahl, Lesezeit und Choreografie bestimmen den Auftritt.
Bei besonders langen Zahlen wird bis zum Ende des Lauftexts verlängert. Die frühere
Playlist-Dauer bleibt für den klassischen Modus gespeichert, wird im neuen Modus
aber nicht verwendet. Playlist und Bitcoin-Seite verwenden dieselbe serverseitige
Berechnung; Angaben sind Näherungen bei langen Zahlen/Blockzeremonien.
Nach der Lesephase folgt ausschließlich ein künstlerischer Übergang, keine erneute
Beschriftung der alten Info oder zusätzliche ALT-/FEHLT-Tafel. Statusmarkierungen
bleiben während der Lesephase sichtbar. Schlaf darf jederzeit unterbrechen.

## Daten und Ehrlichkeit

- Preisquelle weiterhin `BTC_API_URL`; CoinGecko-Aufruf ergänzt
  `include_24hr_change=true`. 24h-Änderung ist **nicht** der Trend seit letzter Abfrage.
- Sats/€ = 100 Millionen / EUR-Preis. Anzeige gerundet; Preis K/M komprimiert.
- Blockhöhe weiterhin `BTC_BLOCK_HEIGHT_API_URL`. Halving ist das nächste Vielfache
  von 210.000 Blöcken, kein geschätztes Datum. Bei Ende der Subventionsära „ENDE“.
- Neue optionale Datenquelle `BTC_NETWORK_API_URL`, Standard
  `https://mempool.space/api`: Gebührenempfehlungen und Timestamp genau des
  abgefragten Blocks. Block-ID, Höhe und Timestamp werden validiert; konkurrierende
  Höhensprünge können keine unpassende Blockzeit veröffentlichen.
- Gebührenprofil sparsam / ca. Stunde / ca. halbe Stunde / schnell auswählbar.
  Kein garantierter Bestätigungszeitpunkt und keine absolute Transaktionsgebühr.
- Alter ist die Zeit seit Block-Timestamp, keine Vorhersage des nächsten Blocks.
- Werte werden pro Vorstellung eingefroren. Abruffehler oder über fünf Minuten
  alte Abrufzeiten erzeugen „ALT“ plus orange-rote Markierung; fehlende/ungültige
  Werte „--“ und „FEHLT“. Werte werden nicht erfunden, Ausfälle blockieren keine
  Rotation. Abrufe laufen unabhängig vom Renderer, mit Timeout und mindestens
  60 Sekunden Abstand für Gebühren/Blockmetadaten.

## Ereignisse und Vorschauen

Drei sechssekündige Neue-Block-Zeremonien: Andocken, Schmieden, Zählerwechsel.
Vor dem nächsten Bitcoin-Besuch, zusätzlich zur regulären Info-Maximalzahl.
Nur bei neu beobachteter Höhe +1 mit frischem vorherigem/nächsten Abruf; keine
Feier bei Initialisierung, Reorg, größerem Sprung, langer Unterbrechung oder Schlaf.
Maximale Verspätung 120 Sekunden; nur neuestes Ereignis statt Warteschlange.
Ereignisse verändern nicht die faire Info-Rotation. Bereits laufende Inhalte
werden nicht abrupt für Bitcoin unterbrochen.

Browser-Vorschau (ein Wert oder eine vollständige Beispielvorstellung) off-thread,
serialisiert mit höchstens vier Anfragen/Sekunde, pausiert bei versteckter Seite.
Live-Daten sind Standard; Beispieldaten und simulierte Blockereignisse sind deutlich
markiert. Eine Simulation nutzt erfundene Höhen und **darf nie** auf LEDs starten.
Echte LED-Vorschau startet direkt ohne Bestätigungsdialog und verwendet auch
ungespeicherte Optionen, ausschließlich echte Daten. Im Schlafmodus HTTP 409,
kein stilles Aufwecken; erst ausdrücklich „Wach“ wählen.

Gemeinsamer Vorschau-Slot für Bitcoin und Time-Stage: eine neue Vorschau ersetzt
die vorherige, keine Warteschlange. Normale Slots, GIFs, laufende Bitcoin- und
Time-Stage-Vorstellungen werden mit angepassten Zeitmarken fortgesetzt, ohne dabei
eine neue reguläre Rotation zu verbrauchen. Keine Einstellung wird durch Vorschauen
gespeichert. Der Header lässt sich auf eine schmale Statuszeile einklappen; die Wahl
bleibt pro Browser beim Seitenwechsel erhalten. Bitcoin-Details sind einklappbar,
Szenen kompakte Zeilen mit direktem LED-Vorschauknopf, Speichern erscheint nur bei
ungespeicherten Änderungen.

Offline-Galerie: `python scripts/preview-bitcoin.py --output OUTPUT_DIRECTORY`.
Zehn Geschichten, drei Ereignisse, Pause/Reduced-Motion, nur markierte Beispieldaten.
Generierte GIFs sind Deployment-Artefakte, nicht im Quellrepository gespeichert.

Neue Einstellungen ergänzen alte BTC-Einstellungen zur Laufzeit ohne DB-Migration
oder Überschreiben alter Farben/Name/Order/Enabled/Dauer. `bitcoin_stage=false`
nutzt weiterhin die vorherige Darstellung. Eigene Farbpaletten gelten bei neuen
Szenen; die bisherigen Farbregler bleiben für die alte Darstellung erhalten.

Tests: Datenvalidierung, faire Reihenfolge/Zufall, Auswahl, eingefrorene Besuche,
Ereignis-/Schlaf-/Vorschau-Sicherheit, alle 70 Stil×Info-Kombinationen, Display-
Zeitgrenzen, API-Authentifizierung, persistente Einstellungen und mobiler Browser.
Kein Langzeit-Stabilitätstest; physische Szenenwirkung muss vor Ort geprüft werden.
