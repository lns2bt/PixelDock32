import asyncio
import datetime
import importlib.util
import logging
import os
import platform
import time
from contextlib import suppress

import httpx

from app.config import Settings

try:
    import Adafruit_DHT
except ImportError:  # pragma: no cover - optional on non-RPi systems
    Adafruit_DHT = None

try:
    import adafruit_dht
    import board
except ImportError:  # pragma: no cover - optional on non-RPi systems
    adafruit_dht = None
    board = None

try:
    import RPi.GPIO as GPIO
except ImportError:  # pragma: no cover - optional on non-RPi systems
    GPIO = None

logger = logging.getLogger(__name__)

def _module_available(module_name: str) -> bool:
    with suppress(Exception):
        return importlib.util.find_spec(module_name) is not None
    return False


def _module_version(distribution_name: str) -> str | None:
    try:
        from importlib.metadata import version

        return version(distribution_name)
    except Exception:  # noqa: BLE001
        return None


BCM_TO_BOARD_PIN = {
    2: "D2",
    3: "D3",
    4: "D4",
    5: "D5",
    6: "D6",
    7: "D7",
    8: "D8",
    9: "D9",
    10: "D10",
    11: "D11",
    12: "D12",
    13: "D13",
    14: "D14",
    15: "D15",
    16: "D16",
    17: "D17",
    18: "D18",
    19: "D19",
    20: "D20",
    21: "D21",
    22: "D22",
    23: "D23",
    24: "D24",
    25: "D25",
    26: "D26",
    27: "D27",
}


class ExternalDataService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache: dict = {
            "btc_eur": None,
            "weather_temp": None,
            "weather_outdoor_temp": None,
            "weather_indoor_temp": None,
            "weather_indoor_humidity": None,
            "btc_updated_at": None,
            "weather_updated_at": None,
            "btc_error": None,
            "weather_error": None,
            "weather_source": "api",
            "dht_updated_at": None,
            "dht_error": None,
            "dht_gpio_level": None,
            "dht_last_attempt_at": None,
            "dht_last_duration_ms": None,
            "dht_raw_temperature": None,
            "dht_raw_humidity": None,
            "dht_processing": None,
            "btc_trend": "flat",
            "btc_block_height": None,
            "btc_block_height_updated_at": None,
            "btc_block_height_error": None,
        }
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        self._running = True
        self._tasks = [
            asyncio.create_task(self._poll_btc()),
            asyncio.create_task(self._poll_weather()),
            asyncio.create_task(self._poll_btc_block_height()),
        ]
        if self.settings.dht_enabled:
            self._tasks.append(asyncio.create_task(self._poll_dht()))

    async def stop(self):
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _poll_btc(self):
        while self._running:
            try:
                async with httpx.AsyncClient(timeout=8) as client:
                    response = await client.get(
                        self.settings.btc_api_url,
                        params={"ids": "bitcoin", "vs_currencies": "eur"},
                    )
                    response.raise_for_status()
                    new_price = response.json()["bitcoin"]["eur"]
                    old_price = self.cache.get("btc_eur")
                    if old_price is None:
                        self.cache["btc_trend"] = "flat"
                    elif new_price > old_price:
                        self.cache["btc_trend"] = "up"
                    elif new_price < old_price:
                        self.cache["btc_trend"] = "down"
                    else:
                        self.cache["btc_trend"] = "flat"
                    self.cache["btc_eur"] = new_price
                    self.cache["btc_updated_at"] = time.time()
                    self.cache["btc_error"] = None
            except Exception as exc:  # noqa: BLE001
                logger.warning("BTC polling failed: %s", exc)
                self.cache["btc_error"] = str(exc)
            await asyncio.sleep(self.settings.poll_btc_seconds)

    async def _poll_weather(self):
        while self._running:
            try:
                async with httpx.AsyncClient(timeout=8) as client:
                    response = await client.get(
                        self.settings.weather_api_url,
                        params={
                            "latitude": self.settings.weather_lat,
                            "longitude": self.settings.weather_lon,
                            "current": "temperature_2m,relative_humidity_2m",
                        },
                    )
                    response.raise_for_status()
                    current = response.json()["current"]
                    self.cache["weather_outdoor_temp"] = current["temperature_2m"]
                    self.cache["weather_temp"] = self.cache["weather_outdoor_temp"]
                    self.cache["weather_source"] = "api"
                    self.cache["weather_updated_at"] = time.time()
                    self.cache["weather_error"] = None
            except Exception as exc:  # noqa: BLE001
                logger.warning("Weather polling failed: %s", exc)
                self.cache["weather_error"] = str(exc)
            await asyncio.sleep(self.settings.poll_weather_seconds)

    async def _poll_dht(self):
        model = self.settings.dht_model.strip().upper()

        while self._running:
            started = time.perf_counter()
            self.cache["dht_last_attempt_at"] = time.time()
            self.cache["dht_gpio_level"] = self._read_gpio_level()
            try:
                humidity, temperature = await asyncio.to_thread(self._read_dht, model)
                if humidity is None or temperature is None:
                    raise RuntimeError("DHT read returned no data")
                raw_temp = float(temperature)
                raw_humidity = float(humidity)
                self.cache["dht_raw_temperature"] = raw_temp
                self.cache["dht_raw_humidity"] = raw_humidity
                self.cache["weather_indoor_temp"] = round(raw_temp, 1)
                self.cache["weather_indoor_humidity"] = round(raw_humidity, 1)
                self.cache["dht_processing"] = self._build_dht_processing(raw_humidity, raw_temp)
                self.cache["weather_source"] = "dht"
                self.cache["dht_updated_at"] = time.time()
                self.cache["weather_updated_at"] = self.cache["dht_updated_at"]
                self.cache["weather_error"] = None
                self.cache["dht_error"] = None
            except Exception as exc:  # noqa: BLE001
                logger.warning("DHT polling failed: %s", exc)
                self.cache["dht_error"] = str(exc)
            finally:
                self.cache["dht_last_duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
                self.cache["dht_gpio_level"] = self._read_gpio_level()
            await asyncio.sleep(self.settings.poll_dht_seconds)

    def _read_dht(self, model: str) -> tuple[float | None, float | None]:
        if Adafruit_DHT:
            sensor = Adafruit_DHT.DHT22 if model == "DHT22" else Adafruit_DHT.DHT11
            humidity, temperature = Adafruit_DHT.read_retry(sensor, self.settings.dht_gpio_pin)
            return humidity, temperature

        if adafruit_dht is None or board is None:
            raise RuntimeError(
                "No DHT backend available (install Adafruit_DHT legacy package or adafruit-circuitpython-dht + adafruit-blinka)"
            )

        pin_name = BCM_TO_BOARD_PIN.get(self.settings.dht_gpio_pin)
        if not pin_name or not hasattr(board, pin_name):
            raise RuntimeError(f"Unsupported DHT GPIO pin for CircuitPython backend: {self.settings.dht_gpio_pin}")

        pin = getattr(board, pin_name)
        sensor = adafruit_dht.DHT22(pin, use_pulseio=False) if model == "DHT22" else adafruit_dht.DHT11(pin, use_pulseio=False)
        try:
            temperature = sensor.temperature
            humidity = sensor.humidity
            return humidity, temperature
        finally:
            with suppress(Exception):
                sensor.exit()

    def _read_gpio_level(self) -> int | None:
        if GPIO is None:
            return None
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.settings.dht_gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            return int(GPIO.input(self.settings.dht_gpio_pin))
        except Exception:  # noqa: BLE001
            return None

    def _build_dht_processing(self, humidity: float, temperature: float) -> dict:
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        return {
            "timestamp": now_iso,
            "model": self.settings.dht_model.strip().upper(),
            "gpio_pin": self.settings.dht_gpio_pin,
            "raw": {"temperature": temperature, "humidity": humidity},
            "processed": {
                "weather_indoor_temp": round(float(temperature), 1),
                "weather_indoor_humidity": round(float(humidity), 1),
            },
            "pipeline": [
                "GPIO sampled",
                "Adafruit_DHT.read_retry decoded pulse timings",
                "values rounded to 1 decimal",
                "cache updated for weather module",
            ],
        }


    def get_gpio_environment_report(self) -> dict:
        backend = "RPi.GPIO" if GPIO is not None else "unavailable"
        problems: list[str] = []

        gpiomem_exists = os.path.exists("/dev/gpiomem")
        gpiomem_rw = os.access("/dev/gpiomem", os.R_OK | os.W_OK) if gpiomem_exists else False
        devmem_exists = os.path.exists("/dev/mem")
        devmem_rw = os.access("/dev/mem", os.R_OK | os.W_OK) if devmem_exists else False

        if GPIO is None:
            problems.append("RPi.GPIO konnte nicht importiert werden")
        if not gpiomem_exists and not devmem_exists:
            problems.append("Weder /dev/gpiomem noch /dev/mem vorhanden")
        if gpiomem_exists and not gpiomem_rw:
            problems.append("Keine RW-Berechtigung auf /dev/gpiomem")

        can_setup_input = False
        input_error = None
        try:
            if GPIO is not None:
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self.settings.dht_gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                _ = int(GPIO.input(self.settings.dht_gpio_pin))
                can_setup_input = True
        except Exception as exc:  # noqa: BLE001
            input_error = str(exc)
            problems.append(f"GPIO setup/input fehlgeschlagen: {exc}")

        return {
            "ok": len(problems) == 0,
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "python": platform.python_version(),
            },
            "gpio": {
                "backend": backend,
                "dht_gpio_pin": self.settings.dht_gpio_pin,
                "can_setup_input": can_setup_input,
                "input_error": input_error,
                "dev_gpiomem_exists": gpiomem_exists,
                "dev_gpiomem_rw": gpiomem_rw,
                "dev_mem_exists": devmem_exists,
                "dev_mem_rw": devmem_rw,
            },
            "libraries": {
                "RPi.GPIO_importable": _module_available("RPi.GPIO"),
                "Adafruit_DHT_importable": _module_available("Adafruit_DHT"),
                "adafruit_dht_importable": _module_available("adafruit_dht"),
                "board_importable": _module_available("board"),
                "RPi.GPIO_version": _module_version("RPi.GPIO") or _module_version("rpi-lgpio"),
                "Adafruit_DHT_version": _module_version("Adafruit_DHT"),
                "adafruit_circuitpython_dht_version": _module_version("adafruit-circuitpython-dht"),
                "adafruit_blinka_version": _module_version("Adafruit-Blinka"),
            },
            "problems": problems,
            "hint": "Wenn GPIO-Zugriff fehlschlägt: App direkt auf dem Raspberry Pi als lokaler User mit GPIO-Rechten starten (kein unprivilegierter Container).",
        }


    def run_gpio_output_test(self, gpio_pin: int, pulses: int = 3, hold_ms: int = 220) -> dict:
        if GPIO is None:
            return {
                "ok": False,
                "gpio_pin": gpio_pin,
                "message": "RPi.GPIO backend not available (on Bookworm install python3-rpi-lgpio)",
            }

        import time as _time

        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(gpio_pin, GPIO.OUT, initial=GPIO.LOW)
            started = _time.perf_counter()
            hold_s = hold_ms / 1000
            for _ in range(pulses):
                GPIO.output(gpio_pin, GPIO.HIGH)
                _time.sleep(hold_s)
                GPIO.output(gpio_pin, GPIO.LOW)
                _time.sleep(hold_s)
            GPIO.output(gpio_pin, GPIO.LOW)
            return {
                "ok": True,
                "gpio_pin": gpio_pin,
                "pulses": pulses,
                "hold_ms": hold_ms,
                "duration_ms": round((_time.perf_counter() - started) * 1000, 2),
                "message": "Output pulse test completed",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "gpio_pin": gpio_pin,
                "message": str(exc),
            }

    def run_gpio_input_probe(self, gpio_pin: int, sample_ms: int = 1000, pull_up: bool = True) -> dict:
        if GPIO is None:
            return {
                "ok": False,
                "gpio_pin": gpio_pin,
                "message": "RPi.GPIO backend not available (on Bookworm install python3-rpi-lgpio)",
            }

        import time as _time

        started = _time.perf_counter()
        high_count = 0
        low_count = 0
        samples = 0
        transitions = 0
        last = None

        try:
            GPIO.setmode(GPIO.BCM)
            pud = GPIO.PUD_UP if pull_up else GPIO.PUD_DOWN
            GPIO.setup(gpio_pin, GPIO.IN, pull_up_down=pud)
            deadline = _time.perf_counter() + (sample_ms / 1000)
            while _time.perf_counter() < deadline:
                value = int(GPIO.input(gpio_pin))
                if value == 1:
                    high_count += 1
                else:
                    low_count += 1
                if last is not None and value != last:
                    transitions += 1
                last = value
                samples += 1
                _time.sleep(0.002)

            ratio_high = (high_count / samples) if samples else 0.0
            ratio_low = (low_count / samples) if samples else 0.0
            state = "mostly_high" if ratio_high > 0.8 else "mostly_low" if ratio_low > 0.8 else "toggling"

            return {
                "ok": True,
                "gpio_pin": gpio_pin,
                "sample_ms": sample_ms,
                "pull": "up" if pull_up else "down",
                "samples": samples,
                "high_count": high_count,
                "low_count": low_count,
                "high_ratio": round(ratio_high, 3),
                "low_ratio": round(ratio_low, 3),
                "transitions": transitions,
                "state": state,
                "duration_ms": round((_time.perf_counter() - started) * 1000, 2),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "gpio_pin": gpio_pin,
                "message": str(exc),
            }

    async def _poll_btc_block_height(self):
        while self._running:
            try:
                async with httpx.AsyncClient(timeout=8) as client:
                    response = await client.get(self.settings.btc_block_height_api_url)
                    response.raise_for_status()
                    self.cache["btc_block_height"] = int(response.text.strip())
                    self.cache["btc_block_height_updated_at"] = time.time()
                    self.cache["btc_block_height_error"] = None
            except Exception as exc:  # noqa: BLE001
                logger.warning("BTC block height polling failed: %s", exc)
                self.cache["btc_block_height_error"] = str(exc)
            await asyncio.sleep(self.settings.poll_btc_seconds)
