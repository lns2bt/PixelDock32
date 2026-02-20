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
