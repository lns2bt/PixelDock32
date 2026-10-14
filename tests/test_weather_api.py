import asyncio
from copy import deepcopy
import time
import unittest
from unittest.mock import Mock, patch

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import weather
from app.api.deps import get_current_user
from app.database import Base, get_db
from app.models import ModuleConfig
from app.services.weather_stage import INFOS, info_value, normalize, presentation_timing


def live_cache():
    now = time.time()
    return dict(weather_outdoor_temp=7, weather_indoor_temp=20,
                weather_indoor_humidity=41, weather_code=61, weather_is_day=True,
                weather_outdoor_updated_at=now, weather_updated_at=now,
                dht_updated_at=now, weather_error=None, dht_error=None)


class WeatherApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with self.sessions() as db:
            row = ModuleConfig(key='weather', name='Weather', duration_seconds=10,
                               enabled=True, sort_order=0,
                               settings={'private_legacy': 'keep', 'weather_stage': False})
            other = ModuleConfig(key='btc', name='Bitcoin', duration_seconds=10,
                                 enabled=True, sort_order=1, settings={})
            db.add_all([row, other])
            await db.commit()
            self.id, self.other_id = row.id, other.id
        self.app = FastAPI()
        self.app.include_router(weather.router)
        self.display = Mock()
        self.display.cache_provider.return_value = live_cache()
        self.display.time_stage = None
        self.display.time_stage_status.return_value = {'sleep': {'active': False}}
        self.display.brightness_lock = asyncio.Lock()
        self.app.state.display_service = self.display

        async def database():
            async with self.sessions() as db:
                yield db
        self.app.dependency_overrides[get_db] = database
        self.app.dependency_overrides[get_current_user] = lambda: 'test'
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.engine.dispose()

    async def stored_settings(self):
        async with self.sessions() as db:
            return deepcopy((await db.get(ModuleConfig, self.id)).settings)

    async def post_preview(self, **options):
        return await self.client.post('/api/weather/preview', json={'module_id': self.id, **options})

    def assert_passive(self):
        self.display.preview_weather.assert_not_called()
        self.display.play_once.assert_not_called()

    async def test_catalog_live_data_and_browser_are_passive(self):
        before = await self.stored_settings()
        cache_before = deepcopy(self.display.cache_provider.return_value)
        response = await self.client.get('/api/weather')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual({style['key'] for style in data['styles']}, {'home', 'station', 'nature', 'neon'})
        self.assertEqual({info['key'] for info in data['infos']}, set(INFOS))
        self.assertEqual(data['data'], [info_value(key, cache_before, normalize({})) for key in INFOS])
        self.assertIn('Modellbasierte', data['source'])
        self.assertIn('konfigurierten Standort', data['source'])
        self.assertEqual(data['sleep'], {'active': False})
        for style in data['styles']:
            response = await self.post_preview(style=style['key'], demo=True, elapsed=4)
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(len(result['pixels']), 256)
            self.assertTrue(result['demo'])
            self.assertIn('text', result)
            self.assertIn('scene_key', result)
            self.assertGreater(result['duration'], 0)
            self.assertEqual(len(result['info']), 2)
        self.assertEqual(await self.stored_settings(), before)
        self.assertEqual(self.display.cache_provider.return_value, cache_before)
        self.assert_passive()

    async def test_unsaved_timing_and_physical_preview_do_not_save(self):
        before = await self.stored_settings()
        options = {'weather_infos': ['humidity', 'conditions', 'inside'],
                   'weather_max_infos': 3, 'weather_read_seconds': 5}
        response = await self.client.post('/api/weather/duration', json={'module_id': self.id, 'settings': options})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), presentation_timing({**before, **options}))
        self.assert_passive()
        response = await self.post_preview(physical=True, style='neon', settings=options)
        self.assertEqual(response.status_code, 200)
        snapshot = self.display.preview_weather.call_args.args[0]
        self.assertEqual(snapshot['weather_infos'], options['weather_infos'])
        self.assertEqual(snapshot['weather_read_seconds'], 5)
        self.assertTrue(snapshot['weather_stage'])
        self.assertEqual(snapshot['weather_styles'], ['neon'])
        self.assertEqual(snapshot['private_legacy'], 'keep')
        response = await self.post_preview(physical=True, info='outside')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.display.preview_weather.call_args.args[0]['weather_infos'], ['outside'])
        self.assertEqual(await self.stored_settings(), before)
        self.display.play_once.assert_not_called()

    async def test_demo_is_fresh_isolated_and_night_is_demo_only(self):
        cache_before = deepcopy(self.display.cache_provider.return_value)
        real_director = weather.Director
        with patch.object(weather, 'Director', wraps=real_director) as director:
            instance = real_director()
            director.return_value = instance
            with patch.object(instance, 'begin', wraps=instance.begin) as begin:
                response = await self.post_preview(demo=True, condition=95, is_day=False)
                self.assertEqual(response.status_code, 200)
                cache = begin.call_args.args[1]
                self.assertTrue(begin.call_args.kwargs['preview'])
                self.assertEqual(cache['weather_code'], 95)
                self.assertIs(cache['weather_is_day'], False)
                self.assertEqual(cache['weather_outdoor_temp'], 12)
                self.assertEqual(cache['weather_indoor_temp'], 22)
                self.assertEqual(cache['weather_indoor_humidity'], 48)
                for key in ('weather_outdoor_updated_at', 'dht_updated_at'):
                    self.assertLess(abs(time.time() - cache[key]), 5)
                self.assertTrue(all(info_value(key, cache, normalize({}))['state'] == 'fresh' for key in INFOS))
        self.assertEqual(self.display.cache_provider.return_value, cache_before)
        for extra in ({'condition': 0}, {'is_day': False}, {'is_day': True}):
            self.assertEqual((await self.post_preview(**extra)).status_code, 422)
        self.assert_passive()

    async def test_hardware_rejects_all_simulation_and_independent_sleep_guards(self):
        for extra in ({'demo': True}, {'condition': 0}, {'is_day': False},
                      {'demo': True, 'condition': 61, 'is_day': True}):
            self.assertEqual((await self.post_preview(physical=True, **extra)).status_code, 422)
        self.display.time_stage_status.return_value = {'sleep': {'active': True}}
        response = await self.post_preview(physical=True)
        self.assertEqual(response.status_code, 409)
        self.assertIn('Wach', response.json()['detail'])
        self.display.time_stage_status.return_value = {'sleep': {'active': False}}
        self.display.time_stage = Mock()
        self.display.time_stage.sleep_state.return_value = {'active': True}
        self.assertEqual((await self.post_preview(physical=True)).status_code, 409)
        self.assert_passive()
        self.display.time_stage.sleep_state.return_value = {'active': False}
        self.display.preview_weather.side_effect = ValueError('Schlafmodus aktiv')
        self.assertEqual((await self.post_preview(physical=True)).status_code, 409)

    async def test_invalid_options_wrong_modules_and_limits(self):
        for extra in ({'style': 'bad'}, {'info': 'bad'}, {'elapsed': -1}, {'elapsed': 301},
                      {'demo': True, 'condition': 4}, {'demo': True, 'condition': True},
                      {'settings': {str(i): i for i in range(129)}}, {'unexpected': True}):
            self.assertEqual((await self.post_preview(**extra)).status_code, 422)
        for value in ('NaN', 'Infinity', '-Infinity'):
            self.assertEqual((await self.post_preview(elapsed=value)).status_code, 422)
        for selection in ([], ['bad'], ['outside', 'bad'], None, 'outside'):
            options = {'weather_infos': selection}
            self.assertEqual((await self.post_preview(settings=options)).status_code, 422)
            self.assertEqual((await self.client.post('/api/weather/duration', json={'settings': options})).status_code, 422)
        for module_id in (99999, self.other_id):
            self.assertEqual((await self.post_preview(module_id=module_id)).status_code, 404)
            self.assertEqual((await self.client.post('/api/weather/duration', json={'module_id': module_id})).status_code, 404)
        self.assertEqual((await self.client.post('/api/weather/duration', json={})).status_code, 200)
        self.assert_passive()

    async def test_all_endpoints_require_authentication(self):
        self.app.dependency_overrides.pop(get_current_user)
        self.assertEqual((await self.client.get('/api/weather')).status_code, 401)
        self.assertEqual((await self.client.post('/api/weather/duration', json={})).status_code, 401)
        self.assertEqual((await self.post_preview()).status_code, 401)
        self.assert_passive()
