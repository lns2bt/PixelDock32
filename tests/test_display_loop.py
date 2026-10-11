import asyncio
from pathlib import Path
import tempfile
import unittest
import time
from unittest.mock import AsyncMock, Mock, patch

from app.config import Settings
from app.services.bitmap_loader import BitmapLoader
from app.services.display import DisplayService
from app.services.led_mapper import LEDMapper
from app.services.rendering import blank_color_frame, blank_frame
from app.modules.base import ModulePayload


class DisplayLoopTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.driver = Mock()
        self.driver.should_force_frame_send.return_value = False
        self.mapper = LEDMapper(Settings(_env_file=None, mapping_state_file=str(Path(directory.name) / "mapping.json")))
        self.display = DisplayService(None, self.driver, self.mapper, lambda: {}, 30, BitmapLoader(Path("app/bitmaps")))

    async def test_initial_black_frame_is_sent_and_unchanged_frame_skipped(self):
        calls = 0

        async def render():
            nonlocal calls
            calls += 1
            if calls == 2:
                self.display._running = False
            return blank_frame(32, 8), blank_color_frame(32, 8)

        self.display._get_next_frame = render
        self.display._running = True
        await self.display._loop()
        self.driver.write_color_frame.assert_called_once_with({})
        self.assertEqual(self.display.unchanged_frame_skips, 1)

    async def test_mapping_revision_resends_unchanged_logical_frame(self):
        calls = 0
        frame, colors = blank_frame(32, 8), blank_color_frame(32, 8)
        frame[0][0], colors[0][0] = 1, (1, 2, 3)

        async def render():
            nonlocal calls
            calls += 1
            if calls == 2:
                self.mapper.set_pixel_fix(logical_x=0, logical_y=0, observed_x=1, observed_y=0)
                self.display._running = False
            return frame, colors

        self.display._get_next_frame = render
        self.display._running = True
        await self.display._loop()
        self.assertEqual(self.driver.write_color_frame.call_count, 2)
        self.assertNotEqual(self.driver.write_color_frame.call_args_list[0], self.driver.write_color_frame.call_args_list[1])

    async def test_start_is_idempotent_and_stop_cancels_task(self):
        self.display._get_next_frame = AsyncMock(return_value=(blank_frame(32, 8), blank_color_frame(32, 8)))
        await self.display.start()
        task = self.display._task
        await self.display.start()
        self.assertIs(self.display._task, task)
        await asyncio.sleep(0)
        await self.display.stop()
        self.assertTrue(task.done())

    async def test_animated_content_does_not_restart_module_transition(self):
        self.display._get_enabled_module_rows = AsyncMock(return_value=[{
            "key": "animations", "duration_seconds": 10,
            "settings": {"transition_ms": 1000, "transition_on_content_change": True},
        }])
        frame1, frame2 = blank_frame(32, 8), blank_frame(32, 8)
        colors1, colors2 = blank_color_frame(32, 8), blank_color_frame(32, 8)
        frame1[0][0], colors1[0][0] = 1, (1, 2, 3)
        frame2[0][1], colors2[0][1] = 1, (4, 5, 6)
        module = Mock(render=AsyncMock(side_effect=[
            ModulePayload(text="", frame=frame1, color_frame=colors1),
            ModulePayload(text="", frame=frame2, color_frame=colors2),
        ]))
        self.display.last_target_key = "textbox"
        clock = Mock(wraps=time)
        clock.monotonic.return_value = 100
        with patch.dict("app.services.display.MODULE_REGISTRY", {"animations": module}), patch("app.services.display.time", clock):
            await self.display._get_next_frame()
            state = self.display.transition_state
            clock.monotonic.return_value = 100.1
            await self.display._get_next_frame()
        self.assertIs(self.display.transition_state, state)
        self.assertEqual(state["start_time"], 100)
        self.assertEqual(self.display.last_target_frame, frame2)
