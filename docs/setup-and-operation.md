# Setup and operation

## Setup

```bash
cd /path/to/PixelDock32
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# only required on Raspberry Pi with DHT sensor:
pip install Adafruit_DHT==1.4.0 --config-settings="--build-option=--force-pi"
# Alternative (if Adafruit_DHT/platform discovery fails):
pip install adafruit-circuitpython-dht adafruit-blinka
# optional GPIO backend fallback (especially with Python 3.13):
# lgpio from pip needs build tools AND the native lgpio library
sudo apt update && sudo apt install -y swig python3-dev liblgpio-dev
pip install lgpio
# Alternative without pip build (system package):
# sudo apt install -y python3-lgpio
cp .env.example .env
```

Optional: Adjust admin password in `.env`.

##Start

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open on the LAN: `http://<raspberrypi-ip>:8000`


## Arduino UNO R3 as LED co-processor (recommended)

1. Open Arduino IDE and flash `arduino/PixelDockUnoR3/PixelDockUnoR3.ino`.
2. Install library: `Adafruit NeoPixel`.
3. Wiring:
   - UNO R3 `D6` -> `DIN` first WS2812B panel
   - UNO R3 `GND` -> Panel `GND` and Raspberry Pi `GND`
   - Use external 5V supply for LED panels (do not power via USB).
4. Connect UNO R3 to the Raspberry Pi via USB.
5. Put in `.env`:

```env
LED_TRANSPORT=serial
LED_SERIAL_PORT=/dev/ttyACM0
LED_SERIAL_BAUDRATE=1000000
# Wait for UNO reset after port open (seconds)
LED_SERIAL_STARTUP_DELAY=2.0
```

Tip: With `LED_TRANSPORT=auto`, the app automatically uses Serial if `rpi_ws281x` is not available.

Note: When opening `/dev/ttyACM0`, the UNO briefly resets R3 via DTR. `LED_SERIAL_STARTUP_DELAY` prevents the first commands (brightness/ping/frames) from falling into the boot phase.

Debug for connection problems: `LED/Serial Debug` and `Serial Ping (Pi ↔ UNO R3)` are now available in the debug UI. This allows you to see transport status, frame counters, last errors and round trip time directly in the web interface.

## systemd autostart

There are now complete step-by-step instructions for productive operation on the Raspberry Pi, including health check recovery in the event of hangs:

- [`docs/autostart-raspberry-pi.md`](autostart-raspberry-pi.md)

Kurzvariante:

```bash
cd /home/pi/PixelDock32
sudo ./scripts/manage-autostart.sh enable --repo-dir /home/pi/PixelDock32 --user pi --group pi
```

## Important .env parameters

- LED driver: `LED_*` (important: `LED_TRANSPORT`, `LED_SERIAL_*`)
- Mapping: `DATA_STARTS_RIGHT`, `SERPENTINE`, `FIRST_PIXEL_OFFSET`
- Rendering/Polling: `RENDER_FPS`, `POLL_BTC_SECONDS`, `POLL_WEATHER_SECONDS`
- Weather/BTC APIs: `WEATHER_*`, `BTC_API_URL`

## Troubleshooting

If the following error occurs when starting:

- `ValueError: the greenlet library is required to use this function. No module named "greenlet"`

Then the Python dependencies were installed incompletely. Reinstall:

```bash
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# optional if DHT is used:
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

Then start `uvicorn app.main:app --host 0.0.0.0 --port 8000` again.


Other common GPIO/DHT errors:

- `RPi.GPIO library not available in this environment`
- `DHT polling failed: Unknown platform.`
- `cannot find -llgpio: No such file or directory`

Cause: App does not run directly on the Raspberry Pi (or without GPIO rights), or the GPIO/DHT libraries are missing in exactly this runtime (venv, service user, container).

Recommended debug method (Web UI):

1. Run **Check GPIO Environment** in the “GPIO Pin Finder” section.
2. Check in the output:
   - `backend` (is `RPi.GPIO` available?)
   - `can_setup_input` and `input_error`
   - `/dev/gpiomem` Existence/Authority
   - detected DHT/GPIO libraries under `libraries`
3. Then start the **Output Test** (LED data pin) and **Input Probe** (sensor pin).
4. In the **Debug & Tools** area, also execute **DHT Read Once** and check whether temperature/humidity or a clear backend error is displayed.

Typical fixes on the Pi:

```bash
# Sample packages depending on distribution
sudo apt update
sudo apt install -y python3-rpi-gpio || sudo apt install -y python3-rpi-lgpio

source .venv/bin/activate
pip install adafruit-circuitpython-dht adafruit-blinka
# if RPi.GPIO is not importable in venv (common on Python 3.13):
# lgpio from pip needs build tools AND the native lgpio library
sudo apt install -y swig python3-dev liblgpio-dev
pip install lgpio
# Alternative without pip build (system package):
# sudo apt install -y python3-lgpio
```

Then restart the app/service.
