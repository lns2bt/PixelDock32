# API Overview (MVP)

- `POST /api/auth/login` → Get JWT
- `GET /api/modules` → Load modules
- `PUT /api/modules/{id}` → Change module
- `POST /api/display/text` → Show instant text
- `POST /api/display/draw` → Show 8x32 pixel frame
- `POST /api/display/brightness` → Set brightness
- `POST /api/debug/pattern` → Start calibration/debug pattern
- `DELETE /api/debug/pattern` → Stop debug pattern
- `GET /api/debug/status` → Runtime/Debug status (FPS, active source, polling status)
- `GET /api/debug/preview` → current 8x32 frame for virtual preview
- `GET /api/debug/mapping/coordinate?x=&y=` → Mapping declaration for single coordinate
- `GET /api/debug/dht` → DHT debug live with GPIO level, raw values, read duration, errors, source/backend statistics, history of the last read attempts and diagnostic recommendation
- `POST /api/debug/dht/read-once` → forced single read including backend, GPIO level before/after read and error details
- `GET /api/debug/led` → LED transport debug (active transport, serial stats, last errors)
- `POST /api/debug/led/serial-ping` → Ping round trip test Raspberry Pi ↔ Arduino UNO R3 via USB serial

## Passive transport measurement (rework)

`GET /api/debug/led/metrics` (Bearer Authentication) provides host side
Frame ACK measurements and transport counters without serial device polling.
Details and measurement procedure: [Tests and measurements](tests-and-measurements.md).

In rework, `GET /api/debug/status` no longer triggers a new serial query.
`GET /api/debug/led` remains an active one, swapped out to a worker thread
diagnosis; Meanwhile, the serial transmitter can briefly access the common I/O lock
wait, but the asyncio render loop is not blocked.
Brightness returns HTTP 503 if device is missing; the desired value remains
saved for the next reconnect. [Details of Phase 2](rework-phase2.md).
