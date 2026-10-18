# Hardware, mapping and calibration

## Hardware mapping notes

- Wiring: `GPIO18 -> rechtes Panel IN -> ... -> linkes Panel`.
- Standard config is designed to:
  - `DATA_STARTS_RIGHT=true`
  - `SERPENTINE=true`
  - `FIRST_PIXEL_OFFSET=0`
  - `PANEL_ORDER=0,1,2,3`
  - `PANEL_ROTATIONS=0,0,0,0`
- Logical API coordinates always remain **left to right**.

## Raspberry Pi + Arduino UNO R3 (USB)

For stable WS2812B signals, the signal generation from the Raspberry Pi is outsourced to the Arduino UNO R3:

- Raspberry Pi: rendering, web servers, sensors, Internet APIs
- Arduino UNO R3: time-critical LED signal processing (`NeoPixel.show()`, PWM/Timing)

### Wiring

- Raspberry Pi USB -> Arduino UNO R3 USB
- Arduino UNO R3 `D6` -> `DIN` of the first WS2812B panel
- Arduino UNO R3 `GND` -> LED GND
- Raspberry Pi `GND` -> LED-GND (common ground recommended)
- Power LED panels via a separate 5V power supply

### Communication protocol (efficient)

The backend sends complete RGB frames in binary form via USB serial to the UNO R3:

- Headers: `P`, `D`, `CMD`, `LEN_LO`, `LEN_HI`
- Payload:
  - `CMD=0x01`: Frame data (`LED_COUNT * 3` bytes, RGB per LED)
  - `CMD=0x02`: brightness (`1` byte)
- Footer: XOR checksum via header + payload

Vorteil:

- hardly any CPU load on the Pi for LED timing
- More robust output with parallel running web server, pollers and sensor access

### Communication behavior (important for debug)

The production sketch is command-based: the UNO **does not** continuously send lines of text like a minimal test sketch. Data/responses only come to valid packets (`CMD_FRAME`, `CMD_BRIGHTNESS`, `CMD_PING`). A pure `readline()` without prior writing can therefore remain empty.

When the serial port is opened, the UNO R3 is typically reset via DTR. The backend therefore waits a configurable short time (`LED_SERIAL_STARTUP_DELAY`, default `2.0s`) before sending the first packets.

### Serial ping debug

To diagnose the USB connection, there is a ping mechanism (`CMD_PING`/`CMD_PING_ACK`), which is available in the web UI under Debug. This allows the Pi↔UNO R3 connection to be checked independently of the image output (including round trip time and error details).

###Firmware

- Path: `arduino/PixelDockUnoR3/PixelDockUnoR3.ino`
- Baud rate: `1000000`
- Arduino library: `Adafruit NeoPixel`

## Fast mapping scheme

If panels have been installed twisted or swapped, you can correct this with two values:

- `PANEL_ORDER`: Order of the **physically linked panels** to the logical panel slots.
  - Format: comma list with 4 numbers (`0..3`)
  - Example `3,2,1,0`: completely mirrored
- `PANEL_ROTATIONS`: Rotation per **logical panel index** in degrees.
  - Allowed: `0`, `90`, `180`, `270`
  - Example `0,180,0,180`: every second panel upside down

Recommended process:

1. Use `panel_walk` until the order matches (`PANEL_ORDER`).
2. Then check the direction of rotation with `pixel_walk` and set the rotation for each panel (`PANEL_ROTATIONS`).
3. Optionally check finally with `border`.

This means you can fix typical hardware errors with just a few numerical values without touching any code.

## Panel calibration & hardware debug

Debug pattern for cabling and mapping check:

- `pixel_walk`: moves through the 8x32 field pixel by pixel
- `panel_walk`: switches 8x8 blocks on a panel-by-panel basis
- `stripes`: flashing vertical stripes
- `border`: static frame

Via the web UI in the **Hardware Debug / Calibration** section or via CLI:

```bash
python3 scripts_calibrate.py --pattern pixel_walk --seconds 30 --interval-ms 200
```

## Mapping Wizard & Virtual Preview

The web UI contains a guided mapping area with:

- Step buttons for panel order/serpentine/edge check
- Coordinate inspector (`x`,`y`) with return of the physical LED index
- Live virtual preview (8x32) via `GET /api/debug/preview`

This allows you to systematically find mapping errors without having to just look at the physical panel.

## DHT11 on Raspberry Pi (local temperature + humidity)

The weather module can optionally read directly from the DHT sensor (instead of Open-Meteo):

1. Wiring DHT11
   - VCC -> 3.3V (Pin 1)
   - GND -> GND (e.g. pin 6)
   - DATA -> GPIO4 (Pin 7, adjustable via `DHT_GPIO_PIN`)
   - With naked sensor: 10k pull-up between DATA and VCC
2. Install Python library:

   Note: If `RPi.GPIO` is missing, first install the OS package for your Raspberry Pi system (e.g. `python3-rpi-gpio` or, depending on the distribution, `python3-rpi-lgpio`).
   ```bash
   pip install -r requirements.txt
   pip install Adafruit_DHT==1.4.0 --config-settings="--build-option=--force-pi"
# Alternative (if Adafruit_DHT/platform discovery fails):
pip install adafruit-circuitpython-dht adafruit-blinka
# optional GPIO backend fallback (especially with Python 3.13):
# lgpio from pip needs build tools AND the native lgpio library
sudo apt update && sudo apt install -y swig python3-dev liblgpio-dev
pip install lgpio
# Alternative without pip build (system package):
# sudo apt install -y python3-lgpio
   ```
3. Activate in `.env`:
   ```env
   DHT_ENABLED=true  # default aktiv
   DHT_MODEL=DHT11
   DHT_GPIO_PIN=4
   POLL_DHT_SECONDS=15
   ```

Notes:
- The weather module rotates compactly between 3 screens: `Oxx.xC` (outdoor), `Ixx.xC` (indoor), `Hxx%` (indoor humidity).
- The switching time can be set in the module via `Screen-Wechsel (Sek.)`.
- Data sources: Outdoor from Open-Meteo, Indoor/Humidity from DHT11.

### Briefly explained: Signal processing & GPIO (DHT11 ↔ Raspberry Pi)

- **Line/Protocol:** The DHT11 uses a single **DATA line** (single-wire, proprietary timing protocol).
- **GPIO assignment:** In this project DATA depends on **BCM GPIO4** (`DHT_GPIO_PIN=4`) by default, supply via **3.3V** and **GND**.
- **Signal stability:** A **pull-up (typically 10kΩ)** between DATA and 3.3V keeps the signal HIGH in idle state.
- **Measuring sequence in the app:** The DHT bollard in `ExternalDataService` cyclically calls `Adafruit_DHT.read_retry(...)`. The library generates the necessary timing sequences on the GPIO and decodes temperature/humidity from them.
- **Further processing:** The decoded values are stored in the cache as `weather_indoor_temp` and `weather_indoor_humidity`; Open-Meteo remains separate as `weather_outdoor_temp`.
- **Display:** The weather module switches time-controlled between outdoor temp, indoor temp and indoor humidity.
