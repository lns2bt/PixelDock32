from datetime import datetime, timedelta
import time
import unittest

from app.services.time_stage import NORMAL_SCENES, EVENT_SCENES, SCENES, catalog, render_scene
from app.services.time_stage.core import Canvas


class TimeStageTests(unittest.TestCase):
    def test_catalog_has_twenty_normal_and_ten_special_scenes(self):
        self.assertEqual(len(NORMAL_SCENES), 20)
        self.assertEqual(len(EVENT_SCENES), 10)
        self.assertEqual(len(SCENES), 30)
        for scene in NORMAL_SCENES + EVENT_SCENES:
            self.assertTrue(scene.title and scene.description and scene.seconds)
            self.assertGreaterEqual(scene.duration, 6)
            self.assertLessEqual(scene.duration, 12)
            self.assertTrue(set(scene.events) <= {'hour','half','quarter'})
        self.assertTrue(all(not s.events for s in NORMAL_SCENES))
        self.assertTrue(all(s.events for s in EVENT_SCENES))
        self.assertEqual(len(catalog()), 30)

    def test_all_frames_are_deterministic_valid_rgb_and_actual_time(self):
        for now in (datetime(2026,10,13,0,0,0), datetime(2026,10,13,12,34,29,500000), datetime(2026,10,13,23,59,59,999999)):
            for scene in NORMAL_SCENES + EVENT_SCENES:
                for elapsed in (0,.5,3,7.9,scene.duration,1000):
                    with self.subTest(scene=scene.key,now=now,elapsed=elapsed):
                        payload = render_scene(scene.key,now,elapsed)
                        self.assertEqual(payload, render_scene(scene.key,now,elapsed))
                        self.assertEqual(payload.text, now.strftime('%H:%M'))
                        self.assertEqual(payload.scene_key, scene.key)
                        self.assertEqual(len(payload.color_frame), 8)
                        for bits, row in zip(payload.frame, payload.color_frame):
                            self.assertEqual(len(row), 32)
                            for bit, color in zip(bits, row):
                                self.assertEqual(bit, int(color is not None))
                                if color is not None:
                                    self.assertEqual(len(color), 3)
                                    self.assertTrue(all(type(c) is int and 0 <= c <= 255 for c in color))

    def test_each_normal_scene_visibly_depends_on_wall_clock_seconds(self):
        now = datetime(2026,10,13,12,34,0)
        for scene in NORMAL_SCENES:
            outputs = [repr(render_scene(scene.key,now + timedelta(seconds=s),3).color_frame) for s in (0,1,7,15,30,45,59)]
            self.assertGreater(len(set(outputs)), 2, scene.key)

    def test_designs_are_not_duplicate_frames_and_rollover_uses_new_time(self):
        now = datetime(2026,10,13,23,59,59)
        designs = [repr(render_scene(scene.key,now,3).color_frame) for scene in NORMAL_SCENES]
        self.assertEqual(len(set(designs)), 20)
        for scene in NORMAL_SCENES + EVENT_SCENES:
            result = render_scene(scene.key,now + timedelta(seconds=1),scene.duration)
            self.assertEqual(result.text, '00:00')

    def test_event_animations_move_and_resolve_into_current_time(self):
        now = datetime(2026,10,13,12,0,0)
        target = Canvas()
        target.clock(now)
        for scene in EVENT_SCENES:
            outputs = [repr(render_scene(scene.key,now,s).color_frame) for s in (0,scene.duration*.25,scene.duration*.5,scene.duration)]
            self.assertGreater(len(set(outputs)), 2, scene.key)
            result = render_scene(scene.key,now,scene.duration)
            # All digit pixels must be visible at completion, regardless of palette.
            for y in range(1,6):
                for x in range(6,25):
                    if target.colors[y][x] is not None:
                        self.assertIsNotNone(result.color_frame[y][x], (scene.key,x,y))

    def test_new_scene_input_validation(self):
        now = datetime(2026,10,13)
        with self.assertRaises(ValueError): render_scene('../secret',now)
        for value in (float('nan'),float('inf')):
            with self.assertRaises(ValueError): render_scene(NORMAL_SCENES[0].key,now,value)

    def test_representative_rendering_stays_in_small_frame_budget(self):
        now = datetime(2026,10,13,12,34,45)
        start = time.perf_counter()
        for i in range(20):
            for scene in NORMAL_SCENES + EVENT_SCENES:
                render_scene(scene.key,now,i/3)
        self.assertLess(time.perf_counter()-start, 8, '600 tiny frames should remain bounded even on the Pi')
