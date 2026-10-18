# Phase 2: stabilized Uno data path

> Historical phase-2 implementation notes. Later releases build on this work;
> the local-only deployment statements and test counts below apply to that phase.

## What changes

- Default now **30 FPS**; an existing `.env` with `RENDER_FPS=20` remains
  remains effective. This is a target value, not yet proof of hardware measurement.
- Renderloop uses continuous monotonous deadlines and skips missed ones
  appointments, instead of delivering old frames as a burst after a dropout.
- Expiry times, module rotation, scrolling and transition progress use monotone
  time. Time, weather/BTC timestamp and UI end timestamp remain calendar time.
- Initial black image and mapping changes are actually sent.
- Module transitions retain their timeline even when the incoming image animates
  is. Animations, bitmaps and marquee do not solve one every frame
  new content transition.
- Web endpoints for LED diagnostics, ping, brightness and sensor/GPIO operations
  perform blocking work in worker threads. Hardware access to the
  serial connections remain exclusively serialized through the same I/O lock.
  There is still a frame sender thread, **not a completely new one
  Command dispatcher**. DHT single reads and pollers share a sensor lock.
- Normal status polling no longer triggers a new serial device query.
- If a USB device is missing, a visibly separated serial backend remains with reconnect,
  instead of permanently switching to mock. `auto` now prefers serial independent
  of installed GPIO packages. For development explicitly `LED_TRANSPORT=mock`.
- Failed static frames are redone without new browser/render action
  tried. New waiting frames still have priority; Have retry/reconnect
  a configurable distance (`LED_SERIAL_RECONNECT_DELAY`, default 1 s).
- During a static display, the transmitter checks after approximately 2 s without
  Traffic the firmware status. USB failure, empty frame counter after reset and
  Differing brightness triggers recalibration. While ongoing
  Animation there are no additional periodic status packages.
- Transport shutdown stops retry wait times, terminates the transmitter and closes
  only then the port. FastAPI also cleans up after initialization errors.
- Short serial writes and contradictory response lengths are rejected.
- Serial/auto validate the fixed Uno geometry: 256 LEDs / 32×8.

## Firmware protocol v3

RGB full frames and frame ACK remain unchanged from v2.

| Command | Payload | Answer |
| --- | --- | --- |
| `0x06` Brightness v3 | 1 byte, 0..255 | `0x86`, 1 byte applied brightness |

The Uno only responds after brightness processing and if necessary
executed LED output. The Pi holds the I/O lock until the response; at this time
no further command or frame begins. The render loop is then forced
a complete image to the lossy internal NeoPixel brightness scaling
to reconstruct from the original RGB values.

While a frame is being received, its LED buffer is considered invalid. Just a complete
A received frame with a valid checksum makes it valid again. Brightness commands
are not allowed to **display** an invalid buffer. Such a command continues to set
the brightness and confirms it; the next valid full image produces the output.
This doesn't require a second 768 byte buffer on the Uno.

### Compatibility

- **v3 recommended:** Frame and brightness commands are confirmed; Protection from
  visible partial/error frames when brightness changes.
- **v2 Transitional operation:** Frame ACK present; before follow-up commands according to brightness
  The Pi waits for processed host TX data and an additional approx. 27.7 ms
  (LED output time + 20 ms reserve). This is a conservative protection time,
  **no willingness confirmed by the UN and no guarantee against any
  delayed USB bridges**. The old sketch has no invalid buffer protection.
- **v1 or failed protocol probe:** no more unacknowledged frames;
  Connection remains in visible error/reconnect state. Update firmware.
- Older Pi application can still use the v3 firmware via the received
  Operate v2 commands. For a clean rollback, they still belong together
  Use Pi/firmware versions.

## Local validation

- **64 local tests successful** (Python 3.14); additionally successful AVR build.
- Hardware-free Python tests: protocol, v2/v3 brightness, short writes, static
  Repeat, reset, shutdown, frame pacing and mapping reissue.
- ASGI contention test: During a blocked hardware operation, the
  passive measurement route accessible. Full app lifespan with SQLite temporary database
  and explicit mock output is also tested.
- Native C++ tests compile the **actual sketch** with host stubs and
  check ACK order, broken frames and timeout/brightness behavior.
  `g++` is required for this; without a compiler, this test is marked as skipped.
- Real Uno build with Arduino CLI **1.2.2**, AVR Core **1.8.6**, Adafruit NeoPixel
  **1.12.3** successful: 5276 bytes flash, 270 bytes static global data.
  In addition, the **768 byte LED buffers are dynamically allocated**; these are
  not included in the 270-byte line of the compiler. There is also stack/heap management.
- GitHub Actions now also includes this pinned firmware build.

None of these tests replace the USB/LED test on the real Pi 3 + Uno.
Nothing was copied to the Pi and no Arduino was flashed.

## Reproducible firmware build (without flashing)

With Arduino CLI 1.2.2 installed:

```bash
arduino-cli core update-index
arduino-cli core install arduino:avr@1.8.6
arduino-cli lib install "Adafruit NeoPixel@1.12.3"
arduino-cli compile --fqbn arduino:avr:uno arduino/PixelDockUnoR3
```

This just creates one build; it deliberately does not contain an upload command.

## Before the next hardware step

1. Back up existing Pi configuration, database, mapping and assets.
2. Record the actual OS/Python version, Uno model and current firmware version.
3. Prepare a baseline or separate test stand on the Pi and flash it explicitly
   release. Test boot/reset/USB and sensor influences on the real hardware.
4. Check a sustained 30 FPS run with [passive measurements](tests-and-measurements.md).

Optical measurement/logic analyzer, CRC instead of XOR, prioritized remain open
Command queue and pixel art asset player. Sender reconnect can also be used for
Arduino boot time may take several seconds; During this time the Pi continues to render
and only keeps the latest waiting image.
