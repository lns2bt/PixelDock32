from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, AsyncMock, patch
from zoneinfo import ZoneInfo

from app.config import Settings
from app.services.bitmap_loader import BitmapLoader
from app.services.display import DisplayService
from app.services.led_mapper import LEDMapper
from app.services.time_stage.settings import Config


class TimeStageDisplayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        settings = Settings(_env_file=None, mapping_state_file=str(Path(temp.name)/'mapping.json'))
        self.driver = Mock()
        self.driver.get_debug_snapshot.return_value = {'brightness':10}
        self.display = DisplayService(None,self.driver,LEDMapper(settings),lambda:{},30,BitmapLoader(Path('app/bitmaps')))
        self.config = Config().model_dump(mode='json')
        self.config['timezone'] = 'UTC'
        self.config['sleep']['enabled'] = False
        self.config['events'] = {key:{**value,'enabled':False} for key,value in self.config['events'].items()}
        self.display.configure_time_stage(self.config)
        self.wall = datetime(2026,10,13,12,34,15,tzinfo=ZoneInfo('UTC'))
        self.display._stage_now = lambda:self.wall
        self.rows = [{'id':1,'key':'textbox','duration_seconds':10,'settings':{'lines':'TEST','transition_ms':0}}]
        self.display._get_enabled_module_rows = AsyncMock(return_value=self.rows)

    async def test_clock_at_boundaries_without_starving_short_interval_playlist(self):
        self.config.update(interval_seconds=1,after_entries=0)
        self.display.configure_time_stage(self.config)
        with patch('app.services.display.time.monotonic',return_value=100):
            await self.display._get_next_frame()
            self.assertEqual(self.display.last_source,'time-stage')
        with patch('app.services.display.time.monotonic',return_value=108):
            await self.display._get_next_frame()
            self.assertEqual(self.display.last_source,'module')
        with patch('app.services.display.time.monotonic',return_value=110):
            await self.display._get_next_frame()
            self.assertEqual(self.display.last_source,'module')
        with patch('app.services.display.time.monotonic',return_value=118):
            await self.display._get_next_frame()
            self.assertEqual(self.display.last_source,'time-stage')

    async def test_count_trigger_is_once_per_completed_slot(self):
        self.config.update(interval_seconds=0,after_entries=2)
        self.display.configure_time_stage(self.config)
        for mono in (100,108,118,119):
            with patch('app.services.display.time.monotonic',return_value=mono):await self.display._get_next_frame()
        self.assertEqual(self.display.time_stage.last_completed,1)
        with patch('app.services.display.time.monotonic',return_value=128):await self.display._get_next_frame()
        self.assertEqual(self.display.last_source,'time-stage')

    async def test_sleep_is_static_and_has_priority_over_manual_debug_and_assets(self):
        self.config['sleep'].update(mode='sleep',until=(self.wall+timedelta(hours=1)).isoformat())
        self.display.configure_time_stage(self.config)
        self.display.set_manual_text('NO',60)
        self.display.set_debug_pattern('stripes',60)
        a=await self.display._get_next_frame()
        self.wall+=timedelta(seconds=1)
        b=await self.display._get_next_frame()
        self.assertEqual(a,b)
        self.assertEqual(self.display.last_source,'sleep')
        self.driver.set_brightness.assert_called_with(1)
        self.assertIsNone(self.display.transition_state)

    async def test_day_brightness_change_during_sleep_waits_until_wake(self):
        self.config['sleep'].update(mode='sleep',until=(self.wall+timedelta(hours=1)).isoformat())
        self.display.configure_time_stage(self.config)
        await self.display._get_next_frame()
        self.display.set_brightness(3)
        self.driver.set_brightness.assert_called_with(1)
        self.config['sleep'].update(mode='wake',until=(self.wall+timedelta(hours=1)).isoformat())
        self.display.configure_time_stage(self.config)
        await self.display._get_next_frame()
        self.driver.set_brightness.assert_called_with(3)

    async def test_physical_preview_requires_sleep_confirmation_and_restores_it(self):
        self.config['sleep'].update(mode='sleep',until=(self.wall+timedelta(hours=1)).isoformat())
        self.display.configure_time_stage(self.config)
        with self.assertRaises(ValueError):self.display.preview_time_stage('retro_cartridge')
        with patch('app.services.display.time.monotonic',return_value=100):
            self.display.preview_time_stage('retro_cartridge',confirm_wake=True)
            await self.display._get_next_frame()
            self.assertEqual(self.display.last_source,'time-stage-preview')
            self.driver.set_brightness.assert_called_with(10)
        with patch('app.services.display.time.monotonic',return_value=109):
            await self.display._get_next_frame()
            self.assertEqual(self.display.last_source,'sleep')
            self.driver.set_brightness.assert_called_with(1)

    async def test_broken_scene_falls_back_to_readable_clock(self):
        with patch('app.services.time_stage.render_scene',side_effect=RuntimeError('broken')):
            result=self.display.render_time_stage_preview('retro_cartridge',self.wall,0)
        self.assertEqual(result.scene_key,'fallback')
        self.assertEqual(result.text,'12:34')
        self.assertTrue(any(any(row) for row in result.frame))

    async def test_roman_duration_rounding_does_not_grow_every_frame(self):
        self.config['scenes']=['craft_roman_scroll'];self.config['intensity']='calm'
        self.display.configure_time_stage(self.config)
        self.wall=self.wall.replace(hour=23,minute=58)
        with patch('app.services.display.time.monotonic',return_value=100):await self.display._get_next_frame()
        end=self.display.time_stage.active['end']
        for mono in (100.1,100.2,101):
            with patch('app.services.display.time.monotonic',return_value=mono):await self.display._get_next_frame()
            self.assertEqual(self.display.time_stage.active['end'],end)

    async def test_browser_astronomy_uses_simulated_date_without_changing_live_data(self):
        self.display.astronomy_data={'date':'LIVE'}
        payload=self.display.preview_for_browser('moonrise',self.wall.replace(month=1),10)
        self.assertEqual(payload.scene_key,'moonrise')
        self.assertEqual(self.display.astronomy_data,{'date':'LIVE'})
