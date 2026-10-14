# GIF-Auswahl und Wiedergabe

## Import vorbereiten

Im Pixel-Studio nach Auswahl der Datei „Import vorbereiten“ öffnen. Bei mehr als
512 Quellframes öffnet sich der Bereich automatisch. Die Analyse speichert nichts.

- **Frames entfernen:** Anzahl am Anfang und Ende eingeben.
- **Zeitbereich behalten:** Start und Ende in Sekunden; leeres Ende bedeutet
  Animationsende. Der Bereich wird nach außen auf vollständige Frames erweitert.
- **Jeden … Frame behalten:** 2 behält jeden zweiten Frame. Die Dauer übersprungener
  Frames wird dem vorherigen behaltenen Frame hinzugefügt, die ausgewählte Laufzeit
  bleibt erhalten. Lange Haltezeiten werden in identische Frames mit höchstens
  2000 ms aufgeteilt; daher reduziert Ausdünnen nicht immer genau um den Faktor.
- Zusammenfassung zeigt Framezahl, Laufzeit, entfernte Sekunden und echte Grenzen.
- „Auswahl als Animation prüfen“ dekodiert nur die Auswahl für die Browser-Vorschau;
  weder Bibliothek, Playlist noch Hardware werden verändert. Erster und letzter
  Frame sind nebeneinander sichtbar, um den Loopübergang zu prüfen.
- Erst „Importieren“ erzeugt ein neues Asset. Originaldatei bleibt unverändert.

Grenzen: 4 MB Upload, maximal 4096 Quellframes für Vorbereitung, 8 Millionen
Quellpixel über die Animation, maximal 1024 Pixel je Seite/262144 Pixel je Bild.
Fertige Assets: maximal 512 Frames, mindestens ein Frame, 33–2000 ms je Frame.
Sehr große Quellbilder müssen weiterhin extern verkleinert werden. Analyse und
Dekodierung finden außerhalb des Renderloops statt, ohne Quellframes zu sammeln.

## Editor

„Bereich kürzen / Frames ausdünnen“ bietet dieselbe Auswahl. „Nur Auswahl abspielen“
prüft den Bereich vor dem Anwenden. „Auf Entwurf anwenden“ ist rückgängig machbar.
„In Bibliothek speichern“ erzeugt immer eine **neue Variante**, überschreibt kein
Asset und tauscht keine Playlist-Referenz aus. Die Variante bei Bedarf in den
Einstellungen des betreffenden Playlist-Moduls auswählen.

## Playlist-Modi

| Modus | Verhalten |
| --- | --- |
| Maximale Dauer (Standard) | Wechsel an der eingestellten Zeitgrenze, auch mitten im Loop. Kurze Loops wiederholen sich. |
| Ein vollständiger Durchlauf | Genau eine Asset-Laufzeit, Dauerfeld ausgeblendet. |
| Zeitlimit + Loop beenden | Wechsel an der ersten Loopgrenze bei oder nach dem Zeitlimit. |

Die Laufzeit berücksichtigt alle Framezeiten und das Tempo: 12 Sekunden Quelle
bei 2× ergeben 6 Sekunden pro Durchlauf. Vorschau der resultierenden Dauer direkt
in der Playlist. „Jetzt“ verwendet dieselbe Regel wie reguläre Wiedergabe.
Time-Stage wartet auf die so definierte Inhaltsgrenze; Schlaf kann weiterhin sofort
unterbrechen. Bitcoin, Textscrolls und die eigenständige Uhr-Regie bleiben unverändert.

Bestehende Asset-Dateien und gespeicherte Modulzeiten werden nicht migriert.
Ohne `settings.playback_mode` gilt jetzt `limit` statt der früher stillschweigenden
Loopverlängerung. `once` und `finish_loop` können pro Asset-Modul gewählt werden.
