from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, AsyncMock, patch
from app.config import Settings
from app.services.bitmap_loader import BitmapLoader
from app.services.display import DisplayService
from app.services.led_mapper import LEDMapper
from app.services.time_stage.settings import Config


class WeatherDisplayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        settings=Settings(_env_file=None,mapping_state_file=str(Path(directory.name)/'mapping.json'))
        self.driver=Mock();self.driver.get_debug_snapshot.return_value={'brightness':10}
        now=time.time()
        self.cache={'weather_outdoor_temp':12,'weather_indoor_temp':22,'weather_indoor_humidity':48,
                    'weather_outdoor_updated_at':now,'weather_outdoor_error':None,'dht_updated_at':now,
                    'dht_error':None,'weather_code':61,'weather_is_day':True}
        self.display=DisplayService(None,self.driver,LEDMapper(settings),lambda:self.cache,30,BitmapLoader(Path('app/bitmaps')))
        self.rows=[dict(id=1,key='weather',duration_seconds=300,settings={}),
                   dict(id=2,key='textbox',duration_seconds=2,settings={'lines':'OK','text_mode':'static'})]
        self.display._get_enabled_module_rows=AsyncMock(side_effect=lambda:self.rows)

    async def frame(self, stamp):
        with patch('app.services.display.time.monotonic',return_value=stamp):
            return await self.display._get_next_frame()

    async def test_automatic_timing_and_fair_rotation_at_real_boundaries(self):
        await self.frame(100)
        visit=self.display._weather_visit
        self.assertEqual([i['key'] for i in visit.infos],['outside','inside'])
        self.assertAlmostEqual(self.display.playlist.deadline,100+visit.duration)
        await self.frame(100+visit.duration+.01)
        self.assertEqual(self.display.last_module_key,'textbox')
        await self.frame(102+visit.duration+.02)
        self.assertEqual([i['key'] for i in self.display._weather_visit.infos],['humidity','conditions'])

    async def test_preview_replaces_and_resumes_without_rotation_consumption(self):
        await self.frame(100);visit=self.display._weather_visit
        with patch('app.services.display.time.monotonic',return_value=103):
            self.display.preview_weather({'weather_infos':['conditions'],'weather_styles':['nature']})
        await self.frame(104);self.assertEqual(self.display.last_source,'weather-preview')
        with patch('app.services.display.time.monotonic',return_value=105):
            self.display.preview_bitcoin({'bitcoin_infos':['fees']})
        await self.frame(106);self.assertEqual(self.display.last_source,'bitcoin-preview')
        await self.frame(116)
        self.assertIs(self.display._weather_visit,visit)
        self.assertEqual(self.display.last_module_key,'weather')
        self.assertAlmostEqual(self.display.playlist.started,113)

    async def test_classic_mode_retains_editable_duration(self):
        self.rows[0].update(duration_seconds=6,settings={'weather_stage':False})
        await self.frame(100);self.assertIsNone(self.display._weather_visit)
        self.assertEqual(self.display.playlist.deadline,106)
        await self.frame(106);self.assertEqual(self.display.last_module_key,'textbox')

    async def test_sleep_interrupts_and_blocks_live_preview(self):
        config=Config().model_dump(mode='json')
        config['sleep'].update(mode='sleep',until=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
        self.display.configure_time_stage(config)
        await self.frame(100);self.assertEqual(self.display.last_source,'sleep')
        with self.assertRaises(ValueError):self.display.preview_weather({})

    async def test_renderer_failure_uses_readable_fallback(self):
        with patch('app.services.weather_stage.render',side_effect=RuntimeError('broken weather')):
            frame,_=await self.frame(100)
        self.assertTrue(any(any(row) for row in frame))
        self.assertEqual(self.display.get_status()['weather_stage']['error'],'broken weather')

    async def test_play_once_uses_choreography_not_playlist_minimum(self):
        with patch('app.services.display.time.monotonic',return_value=100):
            self.display.play_once(Mock(id=1,key='weather',duration_seconds=300,settings={}))
        await self.frame(100)
        self.assertAlmostEqual(self.display._play_once['end'],100+self.display._weather_visit.duration)

    async def test_each_style_has_moving_motifs_and_still_reading(self):
        from app.services.weather_stage import Director, STYLES, INFOS, render
        for style in STYLES:
            for info in INFOS:
                with self.subTest(style=style,info=info):
                    visit=Director().begin({'weather_styles':[style],'weather_infos':[info]},self.cache,preview=True)
                    self.assertNotEqual(render(visit,1.8).color_frame,render(visit,2.9).color_frame)
                    self.assertEqual(render(visit,4).color_frame,render(visit,5).color_frame)
