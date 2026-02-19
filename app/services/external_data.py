import asyncio
import datetime
import logging
import time

import httpx

from app.config import Settings

try:
    import Adafruit_DHT
except ImportError:  # pragma: no cover - optional on non-RPi systems
    Adafruit_DHT = None

try:
    import RPi.GPIO as GPIO
except ImportError:  # pragma: no cover - optional on non-RPi systems
    GPIO = None

logger = logging.getLogger(__name__)


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
        sensor = None
        model = self.settings.dht_model.strip().upper()
        if model == "DHT22":
            sensor = Adafruit_DHT.DHT22 if Adafruit_DHT else None
        else:
            sensor = Adafruit_DHT.DHT11 if Adafruit_DHT else None

        while self._running:
            started = time.perf_counter()
            self.cache["dht_last_attempt_at"] = time.time()
            self.cache["dht_gpio_level"] = self._read_gpio_level()
            try:
                if Adafruit_DHT is None or sensor is None:
                    raise RuntimeError("Adafruit_DHT library not available")
                humidity, temperature = await asyncio.to_thread(
                    Adafruit_DHT.read_retry, sensor, self.settings.dht_gpio_pin
                )
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
