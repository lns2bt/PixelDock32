from datetime import datetime, timedelta
import unittest

from app.services.time_stage import NORMAL_SCENES, SCENES, render_scene
from app.services.time_stage.core import Canvas
from app.services.time_stage.settings import Config
from app.services.time_stage.worlds import SCENES as WORLDS, IVORY, ICE


class ClockWorldsTests(unittest.TestCase):
    def test_registered_as_normal_selectable_scenes(self):
        self.assertEqual(len(WORLDS),5)
        for scene in WORLDS:
            self.assertIs(SCENES[scene.key],scene)
            self.assertIn(scene,NORMAL_SCENES)
            self.assertFalse(scene.events)
            self.assertIn(scene.key,Config().scenes)

    def test_entire_clock_rectangle_is_stable_and_unobstructed(self):
        for hour,minute in ((0,0),(1,11),(8,8),(12,34),(20,20),(23,59)):
            for second in range(60):
                now=datetime(2026,10,15,hour,minute,second,350000)
                for scene in WORLDS:
                    expected=Canvas();expected.clock(now,ICE if scene.key=='world_orbital_station' else IVORY)
                    payload=render_scene(scene.key,now,2)
                    for y in range(1,6):
                        self.assertEqual(payload.color_frame[y][6:25],expected.colors[y][6:25],(scene.key,now,y))

    def test_all_sixty_second_states_are_distinguishable(self):
        base=datetime(2026,10,15,12,34)
        for scene in WORLDS:
            frames={repr(render_scene(scene.key,base+timedelta(seconds=s),3).color_frame) for s in range(60)}
            self.assertEqual(len(frames),60,scene.key)

    def test_motion_uses_wall_time_not_visit_age_or_preview_speed(self):
        for scene in WORLDS:
            now=datetime(2026,10,15,12,34,17,500000)
            self.assertEqual(render_scene(scene.key,now,0),render_scene(scene.key,now,1000))
            before=render_scene(scene.key,now,3)
            after=render_scene(scene.key,now+timedelta(milliseconds=400),3)
            # Gears/train are deliberately discrete; other worlds interpolate.
            if scene.key not in ('world_neon_subway',):
                self.assertNotEqual(before.color_frame,after.color_frame,scene.key)

    def test_rollover_never_shows_previous_minute_or_mutates_configuration(self):
        config=Config(scenes=['retro_scanline'],favorites=['retro_scanline']) if 'retro_scanline' in SCENES else Config(scenes=[NORMAL_SCENES[0].key])
        saved=config.model_dump(mode='json')
        for scene in WORLDS:
            now=datetime(2026,10,15,23,59,59,999999)
            self.assertEqual(render_scene(scene.key,now,8).text,'23:59')
            self.assertEqual(render_scene(scene.key,now+timedelta(microseconds=1),8).text,'00:00')
        self.assertEqual(Config.model_validate(saved).model_dump(mode='json'),saved)
        self.assertEqual(config.scenes,saved['scenes'])

    def test_minute_effect_is_local_not_full_frame_flash(self):
        for scene in WORLDS:
            for stamp in (0,100000,500000,999999):
                payload=render_scene(scene.key,datetime(2026,10,15,12,35,0,stamp),0)
                # Non-digit effects cannot turn the whole panel into bright white.
                bright=sum(color is not None and min(color)>200 for row in payload.color_frame for color in row)
                self.assertLess(bright,100,scene.key)
