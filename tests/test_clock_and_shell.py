"""v0.5.0: digit change styles, showcase clocks, skip and playlist status."""
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

from app.config import Settings
from app.services.bitmap_loader import BitmapLoader
from app.services.display import DisplayService
from app.services.led_mapper import LEDMapper
from app.services.time_stage import NORMAL_SCENES, SCENES, catalog, render_scene
from app.services.time_stage.core import DIGIT_STYLE, DIGIT_STYLES, Canvas
from app.services.time_stage.showcase import SCENE_CONTEXT


def lit(colors):
    return {(x, y) for y, row in enumerate(colors) for x, c in enumerate(row) if c is not None}


class DigitStyleTests(unittest.TestCase):
    def test_every_style_animates_and_settles_on_the_new_time(self):
        settled = Canvas(); settled.clock(datetime(2026, 11, 8, 20, 0, 5))
        for style in DIGIT_STYLES:
            token = DIGIT_STYLE.set(style)
            try:
                frames = []
                for offset in (.05, .2, .35, .5):
                    canvas = Canvas(); canvas.clock(datetime(2026, 11, 8, 20, 0, 0) + timedelta(seconds=offset))
                    frames.append(repr(canvas.colors))
                done = Canvas(); done.clock(datetime(2026, 11, 8, 20, 0, 3))
            finally:
                DIGIT_STYLE.reset(token)
            self.assertGreater(len(set(frames)), 2, style)
            self.assertEqual(lit(done.colors), lit(settled.colors), style)

    def test_scene_default_and_override(self):
        now = datetime(2026, 11, 8, 20, 0, 0, 300000)
        flip = render_scene('craft_mechanical_flip', now, 3)
        rolled = render_scene('craft_mechanical_flip', now, 3, digit_style='roll')
        self.assertNotEqual(flip.color_frame, rolled.color_frame)
        self.assertEqual(render_scene('craft_mechanical_flip', now, 3, digit_style='auto').color_frame, flip.color_frame)
        for scene in NORMAL_SCENES:
            self.assertIn(scene.digit_style, DIGIT_STYLES)

    def test_seconds_digits_animate_within_the_second(self):
        base = datetime(2026, 11, 8, 12, 34, 56)
        frames = {repr(render_scene('retro_cartridge', base + timedelta(seconds=f), 3).color_frame) for f in (.02, .12, .22, .6)}
        self.assertGreaterEqual(len(frames), 3)


class ShowcaseTests(unittest.TestCase):
    def test_new_scenes_are_marked_and_registered(self):
        added = [entry for entry in catalog() if entry['added'] == '0.5.0']
        self.assertEqual({entry['key'] for entry in added},
                         {'show_pendulum', 'show_sky', 'show_nixie', 'show_weather', 'show_aquarium'})

    def test_sky_follows_astronomy_and_falls_back(self):
        tz = ZoneInfo('Europe/Vienna')
        astro = {'sunrise': '2026-11-08T07:10:00+01:00', 'sunset': '2026-11-08T16:45:00+01:00',
                 'civil_dawn': '2026-11-08T06:38:00+01:00', 'civil_dusk': '2026-11-08T17:17:00+01:00'}
        token = SCENE_CONTEXT.set({'astronomy': astro})
        try:
            noon = render_scene('show_sky', datetime(2026, 11, 8, 12, 0, tzinfo=tz), 3).color_frame
            night = render_scene('show_sky', datetime(2026, 11, 8, 23, 0, tzinfo=tz), 3).color_frame
        finally:
            SCENE_CONTEXT.reset(token)
        brightness = lambda frame: sum(sum(c) for row in frame for c in row if c)
        self.assertGreater(brightness(noon), brightness(night))
        # No context at all: still renders a readable clock.
        self.assertTrue(lit(render_scene('show_sky', datetime(2026, 11, 8, 12, 0), 3).color_frame))

    def test_weather_clock_reflects_current_weather(self):
        now = datetime(2026, 11, 8, 12, 0, 5)
        frames = {}
        for category in ('clear', 'rain', 'snow', 'unknown'):
            token = SCENE_CONTEXT.set({'weather': {'category': category, 'is_day': True}})
            try:
                frames[category] = repr(render_scene('show_weather', now, 3).color_frame)
            finally:
                SCENE_CONTEXT.reset(token)
        self.assertEqual(len(set(frames.values())), 4)

    def test_digits_stay_readable_in_showcase_scenes(self):
        now = datetime(2026, 11, 8, 12, 34, 30)
        for key in ('show_pendulum', 'show_sky', 'show_nixie', 'show_weather', 'show_aquarium'):
            frame = render_scene(key, now, 3).color_frame
            self.assertGreater(len(lit(frame)), 20, key)
            self.assertTrue(SCENES[key].description and SCENES[key].seconds)


class SkipAndStatusTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        driver = Mock(); driver.should_force_frame_send.return_value = False
        mapper = LEDMapper(Settings(_env_file=None, mapping_state_file=str(Path(directory.name) / 'mapping.json')))
        self.display = DisplayService(None, driver, mapper, lambda: {}, 30, BitmapLoader(Path('app/bitmaps')))
        self.display._get_enabled_module_rows = AsyncMock(return_value=[
            {'id': 1, 'key': 'textbox', 'duration_seconds': 20, 'settings': {'lines': 'A', 'text_mode': 'static', 'transition_ms': 0}},
            {'id': 2, 'key': 'textbox-b', 'duration_seconds': 20, 'settings': {'lines': 'B', 'text_mode': 'static', 'transition_ms': 0}},
        ])

    async def frame(self, stamp):
        clock = Mock(wraps=time); clock.monotonic.return_value = stamp
        with patch('app.services.display.time', clock):
            await self.display._get_next_frame()
            return self.display.playlist_status()

    async def test_status_reports_progress_and_skip_advances(self):
        status = await self.frame(100)
        self.assertEqual(status['current'], 1)
        status = await self.frame(105)
        self.assertEqual((status['duration_s'], status['elapsed_s'], status['remaining_s']), (20, 5, 15))
        with patch('app.services.display.time.monotonic', return_value=106):
            self.assertTrue(self.display.skip_current())
        status = await self.frame(106.1)
        self.assertEqual(status['current'], 2)
        self.assertIn('playlist', self.display.get_status())

    async def test_skip_without_slot_is_a_noop(self):
        self.assertFalse(self.display.skip_current())


if __name__ == '__main__':
    unittest.main()
