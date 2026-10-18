"""Sleep boundaries, restarts and immediate output restoration without hardware."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

from app.config import Settings
from app.services.bitmap_loader import BitmapLoader
from app.services.display import DisplayService
from app.services.led_mapper import LEDMapper
from app.services.time_stage.engine import TimeStageEngine
from app.services.time_stage.settings import Config


class SleepPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_wake_boundary_restores_day_brightness_and_records_reason(self):
        settings = Settings(_env_file=None, led_transport='mock', led_brightness=12)
        driver = Mock()
        driver.get_debug_snapshot.return_value = {'brightness':12}
        display = DisplayService(None,driver,LEDMapper(settings),lambda:{},30,BitmapLoader(Path('app/bitmaps')))
        config = Config().model_dump(mode='json')
        config['timezone'] = 'Europe/Vienna'
        config['sleep'].update(start='02:00',end='08:00')
        display.configure_time_stage(config)
        display._get_enabled_module_rows = AsyncMock(return_value=[])
        wall = datetime(2026,10,18,7,59,59,tzinfo=ZoneInfo('Europe/Vienna'))
        display._stage_now = lambda:wall
        await display._get_next_frame()
        self.assertEqual(display.last_source,'sleep')
        driver.set_brightness.assert_called_with(1)
        wall += timedelta(seconds=1)
        await display._get_next_frame()
        self.assertNotEqual(display.last_source,'sleep')
        driver.set_brightness.assert_called_with(12)
        history = display.time_stage_status()['sleep_transitions']
        self.assertEqual([entry['active'] for entry in history],[True,False])
        self.assertEqual(history[-1]['mode'],'auto')
        self.assertEqual(history[-1]['timezone'],'Europe/Vienna')

    async def test_explicit_deadline_survives_restarts_without_renewal(self):
        config = Config().model_dump(mode='json')
        config['sleep'].update(enabled=False,mode='sleep',until='2026-10-18T06:00:00Z')
        saved = deepcopy(config)
        for stamp,active in [('2026-10-18T05:59:59Z',True),('2026-10-18T06:00:00Z',False),('2026-10-19T05:59:59Z',False)]:
            for _ in range(2):
                engine = TimeStageEngine(config)
                state = engine.sleep_state(datetime.fromisoformat(stamp))
                self.assertEqual(state['active'],active)
                self.assertEqual(config,saved)
                self.assertEqual(engine.config,saved)

    async def test_dst_boundaries_and_timezone_are_absolute(self):
        config = Config().model_dump(mode='json')
        config['sleep'].update(start='02:30',end='08:00')
        engine = TimeStageEngine(config)
        # Spring's missing 02:30 rolls forward to 03:30 local.
        for stamp,active in [('2026-03-29T01:29:59Z',False),('2026-03-29T01:30:00Z',True),('2026-03-29T06:00:00Z',False),
                             ('2026-10-25T00:29:59Z',False),('2026-10-25T00:30:00Z',True),('2026-10-25T01:30:00Z',True),('2026-10-25T07:00:00Z',False)]:
            instant = datetime.fromisoformat(stamp)
            self.assertEqual(engine.sleep_state(instant)['active'],active,stamp)
            self.assertEqual(engine.sleep_state(instant.astimezone(ZoneInfo('Europe/London')))['active'],active,stamp)

    async def test_same_day_schedule_ends_at_exact_minute(self):
        config = Config().model_dump(mode='json')
        config['sleep'].update(start='00:35',end='17:37')
        engine = TimeStageEngine(config)
        for clock,active in [('00:34:59',False),('00:35:00',True),('17:36:59',True),('17:37:00',False)]:
            now = datetime.fromisoformat('2026-10-18T'+clock+'+02:00')
            self.assertEqual(engine.sleep_state(now)['active'],active)
