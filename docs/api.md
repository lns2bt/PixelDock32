# API-Übersicht (MVP)

- `POST /api/auth/login` → JWT holen
- `GET /api/modules` → Module laden
- `PUT /api/modules/{id}` → Modul ändern
- `POST /api/display/text` → Sofort-Text anzeigen
- `POST /api/display/draw` → 8x32 Pixel-Frame anzeigen
- `POST /api/display/brightness` → Helligkeit setzen
- `POST /api/debug/pattern` → Kalibrier-/Debug-Pattern starten
- `DELETE /api/debug/pattern` → Debug-Pattern stoppen
- `GET /api/debug/status` → Laufzeit-/Debug-Status (FPS, aktive Quelle, Polling-Stand)
- `GET /api/debug/preview` → aktueller 8x32 Frame für virtuelle Vorschau
- `GET /api/debug/mapping/coordinate?x=&y=` → Mapping-Erklärung für einzelne Koordinate
- `GET /api/debug/dht` → DHT-Debug live mit GPIO-Level, Rohwerten, Read-Dauer, Fehlern, Quelle/Backend-Statistiken, Verlauf der letzten Leseversuche und Diagnose-Empfehlung
- `POST /api/debug/dht/read-once` → erzwungener Einzel-Read inkl. Backend, GPIO-Level vor/nach Read und Fehlerdetails
- `GET /api/debug/led` → LED-Transport-Debug (aktiver Transport, Serial-Stats, letzte Fehler)
- `POST /api/debug/led/serial-ping` → Ping Roundtrip-Test Raspberry Pi ↔ Arduino UNO R3 über USB-Serial

## Passive Transportmessung (Rework)

`GET /api/debug/led/metrics` (Bearer-Authentifizierung) liefert hostseitige
Frame-ACK-Messwerte und Transportzähler ohne serielle Geräteabfrage.
Details und Messablauf: [Tests und Messungen](tests-und-messungen.md).

Im Rework löst `GET /api/debug/status` keine neue serielle Abfrage mehr aus.
`GET /api/debug/led` bleibt eine aktive, in einen Workerthread ausgelagerte
Diagnose; währenddessen kann der Serial-Sender kurz auf den gemeinsamen I/O-Lock
warten, der asyncio-Renderloop wird aber nicht blockiert.
Helligkeit liefert bei fehlendem Gerät HTTP 503; der gewünschte Wert bleibt
für den nächsten Reconnect gespeichert. [Details zu Phase 2](rework-phase2.md).
