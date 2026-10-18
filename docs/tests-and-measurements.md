# Phase 1: local testing and passive transport measurement

> This text documents the original phase 1 status. Meanwhile it is
> [Phase 2](rework-phase2.md) implemented: Standard 30 FPS, firmware v3,
> Production shutdown and mandatory frame ACK. Existing `.env` values
> remain effective. The measurement tools described below remain valid.

## Agreed goal and current scope

- Raspberry Pi 3, 1 GB RAM, Raspberry Pi OS (Debian-based, no desktop).
- Arduino Uno remains initially; 256 WS2812B, 32×8 pixels.
- Target after stabilization: steady **30 FPS**.
- Content later: text, sprites/GIFs and procedural animations.

Phase 1 adds testing and host-side metrics. Baud rate, standard FPS,
Protocol and firmware are **not** changed. There is no installation,
no flashing and no access to the Pi.

## Local testing without Pi/Uno

From the repository root directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m unittest discover -s tests -v
```

The test dependencies do not contain Pi/GPIO packages. Python 3.11 or newer
use. GitHub Actions reviews Python 3.11 and 3.13; local became additional
Python 3.14 used. The existing web dependencies can be there
Issue deprecation alerts; their update is not part of phase 1.

Coverage:

- Literal protocol vector, v2 detection, RGB frame, sequence overflow and ping.
- Missing ACK, wrong sequence, broken checksum, retry and reconnect.
- v1 sending does not count as a confirmed ad.
- Waiting frame is replaced; Enqueue copies the image data.
- Sender thread delivers frames; Test Harness then ends it.
- Mapping bijection, panel rotations/order, persistent pixel correction.
- Glyphs, bitmap cache, path limiting and 140 animation combinations.
- Measurement windows, percentiles, idle behavior and memory limits.
- Authenticated passive API without hardware query; Collector error cases.

`tests/fake_uno.py` emulates packets and responses. **It does not emulate AVR timing
nor interrupt locks, USB latency or electrical signals.** Successful tests
therefore do not prove 30 FPS on real hardware. The production shutdown
is still a well-known Phase 2 task; the test cleanup is not a solution for this.

## Passive API

`GET /api/debug/led/metrics` requires the same bearer token as the rest
protected APIs. The route sends no commands to the Uno and does not acquire the
serial I/O lock. It only reads counters and measurements already stored in memory.
The small measurement buffer is limited to 2048 confirmations.

In the serial result:

- `frame_ack_enabled`: confirmed frames can only be measured when v2-ACK is active.
- `counters`: Enqueue, successful sends, replaced frames, ACK/Write errors,
  Retry/reconnect counters and transmitter errors. These are runtime total counters.
  Different counters can move forward during a snapshot;
  they are not an atomic balance of transactions.
- `confirmations.confirmed_frames_total`: successfully confirmed frames since start.
- `confirmed_fps_window`: confirmations per second in the last 30 s window,
  initially based on the shorter term. For buffer overflow `null`, not one
  misleadingly too low FPS number.
- `ack_interval`: p50/p95/p99/max of host-side ACK intervals. A distance counts
  into the window when his final confirmation is in it.
- `successful_attempt_roundtrip`: Duration of successful send/ACK attempt;
  This does not include previous retry/reconnect times. Dropouts appear
  on the other hand, in the ACK intervals or the age of the last confirmation.
- `queue_wait`: Waiting time of the frame before the sender, not total frame latency.
- `last_confirmation_age_ms`: Time since last confirmation, even at standstill.

**Interpretation:** The Uno confirms `strip.show()`. The measurement describes
the receipt of this confirmation on the Pi, not the exact optical time.
USB/OS latency affects them. Static images are intentionally not constant
sent; low confirmed FPS and long ACK intervals are normal there.
No confirmations for mock/GPIO backend or v1 are not proof of a defect
display. The result therefore indicates the actually active backend.

## Later measurement on the Pi via SSH

Only after separate release and backup of `.env`, database, mapping and
Assets use the rework version on the Pi. The following collector assumes
that the server is already running with the new measurement route. An unchanged old one
Server responds to the route with HTTP 404.

For a comparable baseline, initially keep the existing settings
(Default: 20 FPS). Test 30 FPS separately in the stabilization and in each
Note the configuration actually used during the measurement run.

1. Log in to the browser and use the access token from the login response.
   Do not copy tokens to chat, git, or measurement files.
2. SSH to the Pi; Create a private results folder in the repository:

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

The collector only needs Python standard libraries. He only reads
the passive route and **does not change content, brightness or FPS**.
It does not overwrite an existing file, does not follow HTTP redirects and
does not store the token. If you cancel, the previously written samples remain
received. Network/HTTP errors are logged and result in exit code 1;
the output contains rolling statistics, not automatically aggregated ones
10 minute p99 value. You cannot average percentiles of different windows.

## Measuring matrix for later hardware acceptance

Each run as a separate file and with Pi/OS/Python version, firmware version,
Document transport, baud rate, target FPS and selected content:

| Run | Purpose |
| --- | --- |
| Full-screen animation, 10 minutes | Throughput, frame pacing, errors |
| Same animation, debug page open | Impact of existing active debug queries |
| Same animation, additional API operation | Web/Rendering Competition |
| Static image | unchanged frames are skipped |
| Unplug/plug in USB, released separately | Recovery and Reconciliation |

First record the baseline, then again after phase 2 under the same conditions
measure. 30 FPS corresponds to 33.33 ms per image. Specific jitter/recovery limits
set after baseline; 30 FPS has not yet been proven in phase 1.
