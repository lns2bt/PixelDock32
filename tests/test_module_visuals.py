from datetime import datetime
import unittest

from app.services.module_visuals import clock_visual, icon_value
from app.services.display import DisplayService
from app.modules.textbox import TextBoxModule


class VisualTests(unittest.TestCase):
    def test_clock_variants_have_distinct_bounded_rgb_frames(self):
        outputs = []
        for variant in ('classic', 'arcade', 'progress', 'binary', 'orbit', 'neon', 'flip'):
            result = clock_visual(datetime(2026, 10, 13, 23, 59, 42), {'variants':[variant]})
            self.assertEqual(len(result.frame), 8)
            self.assertTrue(all(len(row) == 32 for row in result.frame))
            self.assertTrue(any(any(row) for row in result.frame))
            outputs.append(result.color_frame)
        for i in range(len(outputs)):
            for j in range(i):
                self.assertNotEqual(outputs[i], outputs[j])

    def test_clock_keeps_one_variant_for_entire_visit(self):
        now = datetime(2026,10,13,12,34,56)
        for visit, variant in enumerate(('classic','orbit','neon')):
            for elapsed in (0,4,8,45,120):
                result = clock_visual(now, {'variants':['classic','orbit','neon'], '_visit':visit, '_elapsed':elapsed})
                self.assertEqual(result.scene_key,variant)

    def test_new_clock_animations_move_without_switching_views(self):
        now = datetime(2026,10,13,12,34,56)
        for variant in ('orbit','neon','flip'):
            a = clock_visual(now,{'variants':[variant], '_elapsed':0})
            b = clock_visual(now,{'variants':[variant], '_elapsed':1.2})
            self.assertEqual(a.scene_key,b.scene_key)
            self.assertNotEqual(a.color_frame,b.color_frame)

    def test_symbol_value_fits_panel(self):
        result = icon_value('drop', '100%', (80, 220, 255))
        self.assertEqual(result.text, '100%')
        self.assertEqual(len(result.color_frame), 8)

    def test_fade_endpoints_and_dissolve(self):
        blank = [[0] * 32 for _ in range(8)]
        full = [[1] * 32 for _ in range(8)]
        dark = [[None] * 32 for _ in range(8)]
        lit = [[(100, 150, 200)] * 32 for _ in range(8)]
        for effect in ('fade','dissolve'):
            self.assertEqual(DisplayService._transition(blank,dark,full,lit,1,effect), (full,lit))
            self.assertEqual(DisplayService._transition(blank,dark,full,lit,0,effect), (blank,dark))
        self.assertEqual(DisplayService._transition(blank,dark,full,lit,0,'fade'), (blank,dark))
        frame, colors = DisplayService._transition(blank,dark,full,lit,.5,'fade')
        self.assertEqual(colors[0][0], (50,75,100))

    def test_scroll_duration_covers_all_lines(self):
        lines, widths, speed = TextBoxModule.scroll_cycle({'lines':'HELLO\nPIXEL', 'font_size':'small','scroll_speed':35})
        self.assertEqual(lines, ['HELLO','PIXEL'])
        self.assertTrue(sum(widths) / speed > 2)
