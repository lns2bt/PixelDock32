from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, AsyncMock, patch
from app.config import Settings
from app.services.bitmap_loader import BitmapLoader
from app.services.display import DisplayService
from app.services.led_mapper import LEDMapper
from app.services.time_stage.settings import Config
from test_bitcoin_stage import cache


class BitcoinDisplayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        settings=Settings(_env_file=None,mapping_state_file=str(Path(directory.name)/'mapping.json'))
        self.driver=Mock();self.driver.get_debug_snapshot.return_value={'brightness':10}
        self.cache=cache()
        self.display=DisplayService(None,self.driver,LEDMapper(settings),lambda:self.cache,30,BitmapLoader(Path('app/bitmaps')))
        self.rows=[dict(id=1,key='btc',duration_seconds=3,settings={}),dict(id=2,key='textbox',duration_seconds=2,settings={'lines':'OK'})]
        self.display._get_enabled_module_rows=AsyncMock(return_value=self.rows)

    async def frame(self,mono):
        with patch('app.services.display.time.monotonic',return_value=mono),patch('app.services.display.time.time',return_value=1000):
            return await self.display._get_next_frame()

    async def test_duration_finishes_two_infos_and_rotation_resumes_next_visit(self):
        await self.frame(100)
        self.assertEqual([v['key'] for v in self.display._bitcoin_visit.infos],['price','height'])
        self.assertAlmostEqual(self.display.playlist.deadline,117.4)
        await self.frame(110);self.assertEqual(self.display.last_module_key,'btc')
        await self.frame(118);self.assertEqual(self.display.last_module_key,'textbox')
        await self.frame(120)
        self.assertEqual([v['key'] for v in self.display._bitcoin_visit.infos],['sats','age'])

    async def test_preview_is_independent_and_returns_to_rotation(self):
        row=Mock(id=1,key='btc',duration_seconds=3,settings={'_bitcoin_preview':True,'bitcoin_infos':['fees'],'bitcoin_styles':['orbit']})
        with patch('app.services.display.time.monotonic',return_value=100):self.display.play_once(row)
        await self.frame(100)
        self.assertEqual(self.display._bitcoin_visit.style,'orbit')
        await self.frame(110)
        self.assertEqual([v['key'] for v in self.display._bitcoin_visit.infos],['price','height'])

    async def test_sleep_interrupts_story_and_discards_event(self):
        await self.frame(100);self.cache['btc_block_height']+=1
        config=Config().model_dump(mode='json');config['sleep'].update(mode='sleep',until=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
        self.display.configure_time_stage(config)
        await self.frame(101);self.assertEqual(self.display.last_source,'sleep')
        self.assertIsNone(self.display._bitcoin_directors[1].pending)
        self.driver.set_brightness.assert_called_with(1)

    async def test_renderer_failure_keeps_readable_fallback_and_status(self):
        with patch('app.services.bitcoin_stage.render',side_effect=RuntimeError('broken bitcoin')):
            frame,_=await self.frame(100)
        self.assertTrue(any(any(row) for row in frame))
        self.assertEqual(self.display.get_status()['bitcoin_stage']['error'],'broken bitcoin')

    async def test_automatic_duration_ignores_legacy_playlist_minimum(self):
        self.rows[0]['duration_seconds']=300
        await self.frame(100)
        self.assertAlmostEqual(self.display.playlist.deadline,117.4)
        await self.frame(118)
        self.assertEqual(self.display.last_module_key,'textbox')

    async def test_live_preview_pauses_visit_without_consuming_rotation(self):
        await self.frame(100)
        visit=self.display._bitcoin_visit
        with patch('app.services.display.time.monotonic',return_value=103):
            self.display.preview_bitcoin({'bitcoin_styles':['orbit'],'bitcoin_infos':['fees'],'bitcoin_max_infos':1})
        await self.frame(103)
        self.assertEqual(self.display.last_source,'bitcoin-preview')
        await self.frame(113)
        self.assertIs(self.display._bitcoin_visit,visit)
        self.assertEqual(self.display.last_module_key,'btc')
        self.assertAlmostEqual(self.display.playlist.deadline,127.4)
        await self.frame(128);await self.frame(130)
        self.assertEqual([v['key'] for v in self.display._bitcoin_visit.infos],['sats','age'])

    async def test_new_preview_replaces_old_and_preserves_normal_visit(self):
        await self.frame(100);visit=self.display._bitcoin_visit
        with patch('app.services.display.time.monotonic',return_value=101):self.display.preview_bitcoin({'bitcoin_infos':['fees']})
        with patch('app.services.display.time.monotonic',return_value=102):self.display.preview_bitcoin({'bitcoin_infos':['sats']})
        self.assertEqual(self.display._stage_preview['visit'].infos[0]['key'],'sats')
        await self.frame(120)
        self.assertIs(self.display._bitcoin_visit,visit)
        self.assertAlmostEqual(self.display.playlist.started,119)

    async def test_sleep_boundary_cancels_preview_instead_of_resuming_it_after_wake(self):
        config=Config().model_dump(mode='json')
        config['sleep'].update(mode='wake',until=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
        self.display.configure_time_stage(config)
        with patch('app.services.display.time.monotonic',return_value=100):self.display.preview_bitcoin({})
        config['sleep']['mode']='sleep';self.display.configure_time_stage(config)
        await self.frame(101)
        self.assertIsNone(self.display._stage_preview)
        self.assertEqual(self.display.last_source,'sleep')
        config['sleep']['mode']='wake';self.display.configure_time_stage(config)
        await self.frame(102)
        self.assertNotEqual(self.display.last_source,'bitcoin-preview')
