# Rework: inventory analysis and basis for decision-making

As of October 12, 2026. **No modification to the application or firmware yet.**

## Work area and return point

- Repository: https://github.com/lns2bt/PixelDock32
- Local working copy: `/home/bit/Work/PixelDock32`
- Separate GitHub branch: `rework/smooth-led-pipeline`
- Unchanged output commit: `97a27ec65b662979aa89c619341c3b2ad154f9f2`
- `main` has not been changed. The initial commit remains the exact reference,
  even if `main` is further developed later.

A software rollback must be done later **Pi application and Arduino firmware together**
take into account. Git does not back up the firmware flashed on the Uno or local ones
`.env`, database, mapping status or additionally uploaded image files.
Before a hardware test, these must be backed up separately.

## 1. Existing architecture

```text
Browser on the home network
  → FastAPI / REST / static HTML and JavaScript
  → SQLite module settings + weather/BTC/DHT cache
  → asyncio render loop: 20 FPS by default, 32 × 8 pixels
  → logical image + color matrix → precomputed LED mapping
  → RGB byte buffer → separate serial sender thread
  → USB serial, 1,000,000 baud, PD protocol v2
  → Uno: receive parser, brightness scaling, GRB buffer
  → Adafruit_NeoPixel.show(), D6
  → 256 WS2812B LEDs in one serial chain
```

The browser controls the content; it currently does not deliver every animation frame.
The animations are created on the Pi. The Uno R3 is not a native one
USB frame buffer controller: A USB/UART bridge connects the Pi to the AVR.
The exact bridge (original Uno/Clone) must be confirmed on the hardware.

### Good fundamentals that should be preserved

- Binary full images instead of JSON/text over the serial connection.
- Already 1 Mbaud, sequence numbers and confirmation after the LED output.
- Separate sender thread with only one waiting frame: A new frame replaces
  an old waiting frame instead of creating a growing latency queue.
- Unchanged images will not be retransmitted.
- Mapping lookup is already pre-calculated; Bitmap files are cached.
- HTTP pollers are asynchronous; regular DHT measurements run via `asyncio.to_thread`.
- Debug counters for transport, errors and rendering are present.
- Seven procedural animations consist of text, clock, weather, BTC and bitmap display.

## 2. Time budget: Where is the limit?

For a v2 RGB full screen:

| component | Scope / theoretical time |
| --- | --- |
| Pixel data | 256 × 3 = 768 bytes |
| Sequence + Header + XOR | 8 bytes |
| Pi → Uno, 8N1 at 1 Mbaud | 776 × 10 / 1,000,000 = **7.76 ms** |
| WS2812B data at 800 kbit/s | 256 × 24 / 800,000 = **7.68 ms** |
| Uno → Pi: Frame ACK | 8 bytes = **0.08 ms** UART line time |
| Total | **15.52 ms**, excluding USB/OS/Parser/Latch additional costs |

This corresponds to an idealized upper limit of approximately **64.4 full frames/s**
for the existing stop-and-wait procedure. This is **not measured throughput**.
60 FPS only has 16.67 ms time per image and therefore very little reserve; 30FPS
(33.33 ms) are initially the more reasonable measurement and stability target.

On AVR, NeoPixel output typically disables interrupts during the data phase.
The Uno cannot then operate the normal interrupt-driven UART reception.
**Don't just remove the ACK or blindly pipeline frames:** This is risky
Loss of reception during `show()`. A larger software RX buffer alone solves this
this interrupt lock does not. This also allows AVR time measurement via `millis()`
be influenced; Firmware time values ​​are not automatically reference measurements.

### Possible transport routes, no decision yet

1. **Keep Uno, stabilize RGB v2 first:** lowest hardware risk;
   First prove a consistent 30 FPS, then measure higher rates.
2. **Optional palette-based full screen:** especially suitable for retro pixel art.
   Example with 16 colors: 48 byte palette + 128 byte 4-bit indices + 8 bytes
   Protocol frames result in approximately 184 bytes or 1.84 ms transmission time.
   The LED output remains 7.68 ms; Decoder and protocol need their own tests.
   Keep RGB fallback for gradients, do not reduce colors without asking.
3. **Modern LED controller, e.g. B. RP2040 with PIO or ESP32 with RMT/DMA:**
   Better options for concurrent reception and scheduled output.
   Evaluate USB/Serial implementation and specific board variant separately.
4. **Direct Pi output:** present in project but depends on Pi model,
   Drivers, GPIO and level adjustment. No unchecked standard change.

Consider delta frames/RLE only after measurement: They can help with simple sprites,
but make error handling and status comparison more difficult. Full frames remain
at 256 pixels a simple, robust basis. A higher baud rate alone eliminates neither
the LED output time still has poor frame pacing.

## 3. Specific problems and risks

### P0: Uniformity and operational reliability

- **Blocking debug calls in asyncio web server.** `app/api/debug.py` calls
  Serial diagnostics, ping, DHT individual measurement and GPIO tests synchronously
  `async def` routes. Serial diagnostics waits for the same lock as the transmitter;
  GPIO tests contain sleeps, DHT can repeat for a long time. Meanwhile you can
  the render loop also stops. Status polling can be real serial queries
  trigger (`LEDDriver.get_debug_snapshot`).
- **Brightness command without output confirmation.** The firmware also does for
  Brightness `strip.show()`, but the Pi doesn't wait for it to complete.
  A directly subsequent frame or diagnostic command can be inserted into the
  interrupt-locked output is recommended. A single communication owner with
  An explicit ready/ACK rule for all triggering commands would be cleaner.
- **Automatic fallback to mock output.** In case of hardware initialization errors
  the web server remains active with virtual display; one connected later
  Uno will not automatically activate from this mock state. For development
  helpful, better for production a clear error/reconnect state.
- **Not a clean transport shutdown.** The transmitter has a stop event, but no
  called close/join method. The FastAPI lifespan only stops display and poller.

### P1: Timing, protocol and correct display

- Default is **20 FPS**, not 30/60. Renderloop sleep corrects working time,
  but does not use continuous absolute deadlines; Scheduler delays
  can add up. Animations should have a common monotonic time base
  get. The animation class already uses it, other paths use `time.time()`.
- **“actual_fps” counts render loop runs over the entire runtime**, not that
  images actually confirmed on the display. `last_led_write_ms` measures at
  Serial backend essentially enqueue work, not the complete transfer.
  Current window values and percentiles for displayed frame distances are missing.
- **Enqueue is not display.** The last image created is in the render loop
  immediately saved as the last status. If its transmission fails permanently,
  A static image can then be skipped as “unchanged” as long as
  no successful reconnect sets the resync flag. Target/actual/confirmed status
  separately and guarantee recalibration after errors.
- **XOR is weak error detection.** Certain multi-bit errors remain undetected.
  CRC and resynchronization on subpackets deserve testing. The receptionist writes
  into the NeoPixel buffer before the checksum check; an invalid image becomes
  initially not output, but can be done via a later brightness command
  become visible. This approach would be particularly problematic for delta frames.
- **Static mapping changes do not force a new image** as long as logical
  Frame and colors remain the same. Mapping revision into the output decision
  include.
- **Transitions can disrupt animations.** For `transition_on_content_change`
  Changing animation/scroll frames can trigger new transitions. This
  It makes sense for the animation module to have `transition_ms=0` as default; Module change
  and ongoing animation should still be treated independently.

### P2: Maintainability, pixel art and environment

- Lots of 32×8 constants despite configurable geometry; Pi LED number can vary from
  Fixed at 256 Uno. Validate geometry/log capacity.
- Parallel binary image and color matrix as well as dict/list conversions
  per image. A unified RGB framebuffer format could simplify; at
  Measure 256 pixels first, don't rush into prioritizing micro-optimization.
- Bitmap support is static with vertical scrolling. GIF/APNG/Spritesheets,
  Frame durations and pixel-precise scaling are missing. Retro aesthetics are not alone
  an FPS question: conscious sprite timing and integer positions are important.
- Browser preview polls every second and shows the generated, not necessarily
  the confirmed frame. It is currently not suitable for assessing
  actual display fluid.
- Hardware packages are mandatory in `requirements.txt`; not a separate one
  Desktop/Pi/Test setup. Firmware core and NeoPixel version are not pinned.
- No test suite/CI in checked out state; there is a glyph regression check.
- Configuration defaults contain known login/JWT values. Before productive operation
  require explicit safe values; Check dependencies separately later.
- `LED_TRANSPORT=auto` preferred for importable `rpi_ws281x` Pi-GPIO, not Uno,
  although USB is supposed to be the default path according to the README. Make hardware choice explicit.

## 4. Local checks carried out

Without Pi/Uno connection and without installing hardware packages:

- Python AST syntax check: **34 files successful**, Python 3.14.7.
- `python3 scripts_verify_glyphs.py`: **glyph-regression-ok**.
- Animation smoke check: all 7 presets generate 8×32 images with valid
  RGB channels; An additional 140 preset/palette/mirror combinations are called up.
- 20 warmups + 200 local render measurements per preset:

| Presets | Median (ms) | p95 (ms) |
| --- | ---: | ---: |
| bit_invaders | 0.151 | 0.282 |
| lava_lamp | 1,482 | 3,440 |
| matrix_rain | 0.201 | 0.580 |
| neon_equalizer | 0.547 | 1,019 |
| pixel_snake | 0.154 | 0.363 |
| psychedelic_plasma | 1,152 | 1,767 |
| retro_rainbow_tunnel | 0.845 | 1.366 |

**These values come from the local development computer, not from the Raspberry Pi.**
They only measure `AnimationsModule.render`, not database, mapping, transport or
LED output. No full web server/firmware/hardware test performed.
The missing Python web/serial dependencies were not included for this analysis
installed. No statement about real FPS or optical signal quality is possible.

## 5. Proposal for the rework to be decided upon together

1. **Baseline and reproducible tests:** Protocol, mapping, queue, shutdown
   and failure case testing; simulated Uno without hardware; reproducible firmware builds.
   On the real Pi, measure frame spacing, ACK times, errors and replaced frames.
2. **Stabilize existing RGB path:** Hardware owner, nonblocking API,
   confirmed commands, monotonous deadlines, shutdown, reconnect and resync.
   A steady 30 FPS as the first suggested drop target.
3. **Transport decision after measurement:** Uno + RGB, optional pallet frames or
   modern controller; Only commit to 60 FPS as a goal when there is enough reserve.
4. **Pixel Art Pipeline:** Sprite/Animation assets, time-based player,
   Nearest neighbor/crop, defined palettes, clean module changes and preview.
5. **Cleanup and Operation:** smaller clearly separated components, development
   and hardware dependencies, CI, secure configuration and upgrade/rollback documentation.

Decrease not just through average FPS: suggested series of measurements
full-scale animation, static image, open debug pages, API load and
USB unplugging/plugging in. At least 10 minutes of continuous running; Frame spacing p50/p95/p99,
Document long dropouts, ACK/checksum errors and recovery. Specific limit values
for jitter and reconnection only after hardware baseline.

## 6. Still to be clarified together

Meanwhile confirmed: Raspberry Pi 3 with 1 GB RAM, Raspberry Pi OS without desktop,
32×8 WS2812B pixels, 30 FPS as target, keep Uno for now. Text, sprites/GIFs
and procedural animations should be supported. SSH access is available.
Phase 1 (local testing and measurement basis) has been released; Implementation and limits
are available at [tests and measurements](tests-and-measurements.md).
The following original list of questions is retained for comprehensibility.

- Which Raspberry Pi model, OS and Python version are actually running?
- Original Uno R3 or clone, and which USB/UART bridge?
- Will the display remain with four WS2812B 8×8 panels / 32×8 pixels?
- Is 30 FPS enough, or should 60 FPS be the target under load?
- Does the Uno have to stay, or would a cheaper controller change be possible?
- Desired content: your own sprites, GIFs, game scenes, scrolling text, data modules?
- Which stutters/errors are currently occurring, with which `.env` values?
- How can Pi access and secured hardware testing take place later?
