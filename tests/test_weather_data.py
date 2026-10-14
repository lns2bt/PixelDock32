import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.config import Settings
from app.services.external_data import ExternalDataService, WMO_WEATHER_CODES


class WeatherDataTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = ExternalDataService(Settings(_env_file=None, dht_enabled=False))

    async def poll_weather(self, current=None, *, now=1000, error=None):
        response = Mock()
        response.json.return_value = {"current": current}
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.get = AsyncMock(side_effect=error, return_value=response)
        self.service._running = True

        async def finish(_):
            self.service._running = False

        with patch("app.services.external_data.httpx.AsyncClient", return_value=client), \
             patch("app.services.external_data.asyncio.sleep", side_effect=finish), \
             patch("app.services.external_data.time.time", return_value=now):
            await self.service._poll_weather()
        return client

    async def poll_dht(self, temperature=22, humidity=50, *, now=1000, error=None):
        self.service._running = True

        async def finish(_):
            self.service._running = False

        with patch.object(self.service, "_read_dht", return_value=(humidity, temperature, "test"), side_effect=error), \
             patch.object(self.service, "_read_gpio_level", return_value=None), \
             patch("app.services.external_data.asyncio.sleep", side_effect=finish), \
             patch("app.services.external_data.time.time", return_value=now):
            await self.service._poll_dht()

    async def test_same_request_includes_all_current_fields_and_nighttime_codes(self):
        for code in sorted(WMO_WEATHER_CODES):
            client = await self.poll_weather({
                "temperature_2m": -2.5, "relative_humidity_2m": 83,
                "weather_code": code, "is_day": 0,
                "precipitation": 1.2, "wind_speed_10m": 12.5,
            })
            client.get.assert_awaited_once()
            self.assertEqual(set(client.get.call_args.kwargs["params"]["current"].split(",")), {
                "temperature_2m", "relative_humidity_2m", "weather_code",
                "is_day", "precipitation", "wind_speed_10m",
            })
            cache = self.service.cache
            self.assertEqual(cache["weather_code"], code)
            self.assertIs(cache["weather_is_day"], False)
            self.assertEqual(cache["weather_outdoor_humidity"], 83)
            self.assertEqual(cache["weather_precipitation"], 1.2)
            self.assertEqual(cache["weather_wind_speed"], 12.5)
            self.assertEqual(cache["weather_temp"], -2.5)
            self.assertEqual(cache["weather_source"], "api")
            self.assertEqual(cache["weather_outdoor_updated_at"], 1000)
            self.assertIsNone(cache["weather_outdoor_error"])

    async def test_invalid_temperature_preserves_previous_values_and_stamp(self):
        await self.poll_weather({"temperature_2m": 10, "weather_code": 61})
        for value in (None, True, "20", float("nan"), float("inf"), -91, 71, 10**400):
            with self.subTest(value=value):
                await self.poll_weather({"temperature_2m": value, "weather_code": 0}, now=2000)
                self.assertEqual(self.service.cache["weather_outdoor_temp"], 10)
                self.assertEqual(self.service.cache["weather_code"], 61)
                self.assertEqual(self.service.cache["weather_outdoor_updated_at"], 1000)
                self.assertIsNotNone(self.service.cache["weather_outdoor_error"])
        for value in (-90, 70):
            await self.poll_weather({"temperature_2m": value})
            self.assertEqual(self.service.cache["weather_outdoor_temp"], value)

    async def test_partial_metadata_never_infers_or_retains_old_weather(self):
        await self.poll_weather({"temperature_2m": 10, "weather_code": 61, "is_day": 1})
        for code in (None, 4, -1, 100, "0", True, 0.0):
            await self.poll_weather({
                "temperature_2m": 21, "weather_code": code, "is_day": "false",
                "relative_humidity_2m": 101, "precipitation": -1, "wind_speed_10m": float("nan"),
            })
            for key in ("weather_code", "weather_is_day", "weather_outdoor_humidity",
                        "weather_precipitation", "weather_wind_speed"):
                self.assertIsNone(self.service.cache[key], key)
            self.assertEqual(self.service.cache["weather_temp"], 21)
            self.assertIsNone(self.service.cache["weather_outdoor_error"])
        await self.poll_weather({"temperature_2m": 22})
        self.assertIsNone(self.service.cache["weather_code"])
        for day, expected in ((0, False), (1, True), (False, False), (True, True),
                              (2, None), (1.0, None), ("1", None)):
            await self.poll_weather({"temperature_2m": 22, "is_day": day})
            self.assertIs(self.service.cache["weather_is_day"], expected)

    async def test_optional_numbers_are_finite_and_bounded(self):
        for value in (float("inf"), float("nan"), -1, 1001, "12", True):
            await self.poll_weather({"temperature_2m": 22, "relative_humidity_2m": value,
                                     "precipitation": value, "wind_speed_10m": value})
            for key in ("weather_outdoor_humidity", "weather_precipitation", "weather_wind_speed"):
                self.assertIsNone(self.service.cache[key])
        await self.poll_weather({"temperature_2m": 22, "wind_speed_10m": 501})
        self.assertIsNone(self.service.cache["weather_wind_speed"])

    async def test_offline_and_dht_cannot_mask_outdoor_error_or_refresh_stamp(self):
        await self.poll_weather({"temperature_2m": 10, "weather_code": 95})
        await self.poll_weather(error=RuntimeError("offline"), now=1200)
        await self.poll_dht(now=1300)
        cache = self.service.cache
        self.assertEqual(cache["weather_outdoor_error"], "offline")
        self.assertEqual(cache["weather_outdoor_updated_at"], 1000)
        self.assertEqual(cache["weather_outdoor_temp"], 10)
        self.assertEqual(cache["weather_code"], 95)
        self.assertEqual(cache["dht_updated_at"], 1300)
        self.assertEqual(cache["weather_updated_at"], 1300)
        self.assertIsNone(cache["dht_error"])
        await self.poll_dht(error=RuntimeError("sensor offline"), now=1400)
        self.assertEqual(cache["dht_updated_at"], 1300)
        await self.poll_weather({"temperature_2m": 11}, now=1500)
        self.assertEqual(cache["dht_error"], "sensor offline")
        self.assertEqual(cache["dht_updated_at"], 1300)

    async def test_debug_read_updates_dht_only_and_rejects_invalid_values(self):
        await self.poll_weather(error=RuntimeError("offline"))
        with patch.object(self.service, "_read_gpio_level", return_value=None), \
             patch.object(self.service, "_read_dht", return_value=(48, 23.25, "test")), \
             patch("app.services.external_data.time.time", return_value=2000):
            result = self.service.read_dht_debug_snapshot()
        self.assertTrue(result["ok"])
        self.assertEqual(self.service.cache["weather_indoor_temp"], 23.2)
        self.assertEqual(self.service.cache["dht_updated_at"], 2000)
        self.assertEqual(self.service.cache["weather_outdoor_error"], "offline")
        self.assertIsNone(self.service.cache["weather_outdoor_updated_at"])
        for humidity, temperature in ((101, 22), (50, float("nan")), (-1, 22), (50, 71)):
            with patch.object(self.service, "_read_gpio_level", return_value=None), \
                 patch.object(self.service, "_read_dht", return_value=(humidity, temperature, "test")):
                self.assertFalse(self.service.read_dht_debug_snapshot()["ok"])
            self.assertEqual(self.service.cache["dht_updated_at"], 2000)
            self.assertIsNotNone(self.service.cache["dht_error"])

    async def test_trends_require_real_source_history_and_elapsed_time(self):
        for now, temperature in ((1000, 20), (1100, 20.3), (1200, 20.8)):
            await self.poll_weather({"temperature_2m": temperature}, now=now)
            self.assertIsNone(self.service.cache["weather_outdoor_trend"])
        await self.poll_dht(now=1300)
        self.assertIsNone(self.service.cache["weather_outdoor_trend"])
        await self.poll_weather({"temperature_2m": 21}, now=1300)
        self.assertEqual(self.service.cache["weather_outdoor_trend"], 1)
        for now, temperature, humidity in ((1400, 22, 50), (1600, 21, 54)):
            await self.poll_dht(temperature, humidity, now=now)
        self.assertEqual(self.service.cache["weather_indoor_trend"], -1)
        self.assertEqual(self.service.cache["weather_humidity_trend"], 1)
        self.assertEqual(len(self.service._weather_history["weather_outdoor_trend"]), 4)
        await self.poll_weather(error=RuntimeError("offline"), now=1700)
        self.assertIsNone(self.service.cache["weather_outdoor_trend"])
        self.assertEqual(len(self.service._weather_history["weather_outdoor_trend"]), 4)
        await self.poll_weather({"temperature_2m": 22}, now=5000)
        self.assertIsNone(self.service.cache["weather_outdoor_trend"])
        self.assertEqual(len(self.service._weather_history["weather_outdoor_trend"]), 1)
        await self.poll_dht(now=5000)
        self.assertIsNone(self.service.cache["weather_indoor_trend"])
        self.assertIsNone(self.service.cache["weather_humidity_trend"])

    async def test_two_samples_or_repeated_timestamp_cannot_make_a_trend(self):
        await self.poll_weather({"temperature_2m": 20}, now=1000)
        await self.poll_weather({"temperature_2m": 21}, now=1300)
        self.assertIsNone(self.service.cache["weather_outdoor_trend"])
        for _ in range(3):
            await self.poll_weather({"temperature_2m": 21}, now=1300)
        self.assertEqual(len(self.service._weather_history["weather_outdoor_trend"]), 2)
        self.assertIsNone(self.service.cache["weather_outdoor_trend"])
        await self.poll_weather({"temperature_2m": float("nan")}, now=1400)
        self.assertEqual(len(self.service._weather_history["weather_outdoor_trend"]), 2)
        await self.poll_weather({"temperature_2m": 21}, now=1500)
        self.assertEqual(self.service.cache["weather_outdoor_trend"], 1)

    async def test_trend_deadbands_and_bounded_history(self):
        for now, temperature, humidity in ((1000, 20, 50), (1150, 20.1, 51), (1300, 20.4, 52.9)):
            await self.poll_weather({"temperature_2m": temperature}, now=now)
            await self.poll_dht(temperature, humidity, now=now)
        for key in self.service._weather_history:
            self.assertEqual(self.service.cache[key], 0)
        for index in range(30):
            now = 1600 + index * 300
            await self.poll_weather({"temperature_2m": 20}, now=now)
            await self.poll_dht(now=now)
        for history in self.service._weather_history.values():
            self.assertLessEqual(len(history), 24)
            self.assertEqual(history.maxlen, 24)

    async def test_invalid_dht_poll_does_not_publish_or_create_history(self):
        for temperature, humidity in ((71, 50), (22, 101), (float("inf"), 40), (True, 40)):
            await self.poll_dht(temperature, humidity)
            self.assertIsNone(self.service.cache["dht_updated_at"])
            self.assertIsNone(self.service.cache["weather_indoor_temp"])
            self.assertIsNotNone(self.service.cache["dht_error"])
        self.assertFalse(self.service._weather_history["weather_indoor_trend"])
