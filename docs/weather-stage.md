# Wetter-Stage

Das vorhandene Wetter-Modul bleibt ein regulärer Playlist-Eintrag und erhält
eine eigene Szenen-Regie; es entsteht keine zweite Playlist. Die klassische
Darstellung bleibt mit `weather_stage=false` erhalten, einschließlich ihrer
gespeicherten Optionen und Playlist-Dauer.

## Auswahl und Lesedauer

Vier Stile: **home**, **station**, **nature**, **neon**. Jeder Stil kann jede der
vier Informationen darstellen: Außentemperatur (**outside**), Innentemperatur
(**inside**), Innen-Luftfeuchte (**humidity**) und Wetterbedingungen (**conditions**).
Standardmäßig höchstens **zwei Infos pro Vorstellung**; die Auswahl rotiert fair.
Browser-Vorschauen nutzen einen eigenen Director und verbrauchen keine regulären
Rotationsplätze.

Pixel-Zuhause zeigt Landschaft, Zimmerlicht und Tropfen; Wetterstation animiert
Messskalen, Naturwelt Bäume/Häuschen/Wellen und Neon-Labor leuchtende Messkammern.
Wettercodes wählen Sonne, Mond, Wolken, Regen, Schnee, Nebel oder ein gedämpftes
Gewittermotiv ohne Vollbildblitze/Stroboskop. Während der Lesephase steht die
Darstellung ruhig; A/I/H unterscheiden Außen, Innen und Innenfeuchtigkeit.

Die automatische Gesamtdauer umfasst Einstieg, Beschriftung, Motiv, Übergang,
Lesephase und Ausklang. Die eingestellte Lesezeit ist die eigentliche ruhige
Lesephase, keine zusätzliche Wartezeit nach der Vorstellung. Nach dem Lesen
folgen keine wiederholte Infotafel und keine zusätzliche ALT-/FEHLT-Tafel.
`POST /api/weather/duration` berechnet dieselbe Dauer aus gespeicherten und
ungespeicherten Optionen, ohne Laufzeit oder Rotation zu verändern.

## Quellen und Aktualität

Außentemperatur und Wetterbedingungen stammen aus **modellbasierten Open-Meteo
Current Conditions für den konfigurierten Standort**. Das ist weder eine lokale
Messung noch eine Beobachtung vor dem Fenster. Tag/Nacht und WMO-Wettercode
beschreiben diese Modelldaten; die Animation ist keine echte Wetterereignismeldung.
Innendaten stammen vom konfigurierten DHT-Sensor.

Außendaten haben einen eigenen Abrufzeitstempel und gelten nach **900 Sekunden**
als veraltet. Innentemperatur und Luftfeuchte verwenden ausschließlich den
DHT-Zeitstempel und werden nach **300 Sekunden** als veraltet markiert. Ein
frischer Sensorabruf macht alte Außendaten nicht frisch. Fehler/alte Werte bleiben
erkennbar; fehlende Daten werden nicht erfunden. Werte sind pro Besuch eingefroren.

Trends beruhen auf höchstens 24 echten Samples pro Messgröße, mindestens drei
über fünf Minuten. Richtung erst ab 0,5 °C beziehungsweise drei Prozentpunkten;
bei zu wenigen, alten oder fehlerhaften Messungen keine Trendanzeige.
Wettercode, Tag/Nacht, Niederschlag und Wind werden in derselben Anfrage abgerufen.
Unbekannte Codes führen zu neutralem Motiv, nicht erfundenem Sonnenschein.

## Vorschau und Sicherheit

Alle `/api/weather`-Endpunkte erfordern Anmeldung. `GET /api/weather` liefert
Katalog, Live-Infos, Quellenhinweis und Schlafstatus. Browser-Vorschauen und
Dauerberechnung sind passiv und speichern keine Einstellungen.

`POST /api/weather/preview` berücksichtigt ungespeicherte Optionen. Live-Daten
sind Standard. Nur eine ausdrücklich markierte Browser-Demo darf Wettercode und
Tag/Nacht simulieren, auch Nacht. Ihre frischen Beispieldaten sind 12 °C außen,
22 °C innen, 48 % Luftfeuchte, standardmäßig klarer Tag. Eine Simulation erzeugt
kein echtes Wetterereignis und darf niemals auf die Hardware gelangen.

Eine direkte LED-Vorschau nutzt ausschließlich Live-Daten und den gemeinsamen
Vorschau-Slot: eine neue Vorschau ersetzt die vorherige. Reguläre Vorstellungen
werden pausiert und anschließend fortgesetzt, ohne reguläre Rotation zu verbrauchen.
Auch diese Vorschau speichert nichts und verwendet nicht das gewöhnliche
`play_once`. Im Schlafmodus gilt HTTP 409: erst ausdrücklich **Wach** wählen;
die Vorschau darf weder Schlaf umgehen noch still aufwecken.
