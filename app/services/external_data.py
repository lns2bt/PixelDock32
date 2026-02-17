import asyncio
import logging
import time

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class ExternalDataService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache: dict = {
            "btc_eur": None,
            "weather_temp": None,
            "btc_updated_at": None,
            "weather_updated_at": None,
            "btc_error": None,
            "weather_error": None,
            "btc_trend": "flat",
        }
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        self._running = True
        self._tasks = [
            asyncio.create_task(self._poll_btc()),
            asyncio.create_task(self._poll_weather()),
        ]

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
                            "current": "temperature_2m",
                        },
                    )
                    response.raise_for_status()
                    self.cache["weather_temp"] = response.json()["current"]["temperature_2m"]
                    self.cache["weather_updated_at"] = time.time()
                    self.cache["weather_error"] = None
            except Exception as exc:  # noqa: BLE001
                logger.warning("Weather polling failed: %s", exc)
                self.cache["weather_error"] = str(exc)
            await asyncio.sleep(self.settings.poll_weather_seconds)
