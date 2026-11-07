"""Pipeline, transitions, animations and clock roll of the smooth-motion release."""
import asyncio
from datetime import datetime, timedelta
import time
import unittest

from app.modules.animations import PALETTE_CHOICES, PRESET_INFO, PRESETS, AnimationsModule
from app.services import fx, transitions
from app.services.output_stage import OutputStage
from app.services.rendering import render_text_with_colors
from app.services.time_stage.core import DIGIT_ROLL, ROLL_SECONDS, Canvas


class OutputStageTests(unittest.TestCase):
    def test_gamma_one_is_an_exact_bypass(self):
        stage = OutputStage(1.0)
        frame = {0: (1, 2, 3), 5: (255, 128, 0)}
        self.assertIs(stage.apply(frame, 64), frame)

    def test_firmware_formula_matches_uno_sketch(self):
        self.assertEqual(OutputStage.firmware_scale(200, 255), 200)
        self.assertEqual(OutputStage.firmware_scale(200, 0), 0)
        self.assertEqual(OutputStage.firmware_scale(255, 63), 63)
        self.assertEqual(OutputStage.firmware_scale(100, 127), 50)

    def test_output_is_monotonic_and_white_stays_white(self):
        stage = OutputStage(2.2)
        for brightness in (8, 40, 64, 128, 255):
            physical = []
            for value in range(256):
                sent = stage.apply({0: (value, value, value)}, brightness)[0]
                physical.append(OutputStage.firmware_scale(sent[0], brightness))
            self.assertEqual(physical, sorted(physical), brightness)
            self.assertEqual(physical[-1], OutputStage.firmware_scale(255, brightness))
            self.assertEqual(physical[0], 0)
            # Gamma darkens mid-tones relative to the old linear mapping.
            self.assertLess(physical[128], OutputStage.firmware_scale(128, brightness) + 1)

    def test_dim_pixels_never_vanish_and_keep_their_hue(self):
        stage = OutputStage(2.2)
        sent = stage.apply({0: (5, 3, 13)}, 32)[0]
        physical = [OutputStage.firmware_scale(c, 32) for c in sent]
        self.assertEqual(physical, [0, 0, 1])
        self.assertEqual(stage.apply({1: (0, 0, 0)}, 32)[1], (0, 0, 0))

    def test_temporal_dither_averages_to_target(self):
        stage = OutputStage(2.2, temporal_dither=True)
        levels = [OutputStage.firmware_scale(stage.apply({0: (90, 90, 90)}, 64)[0][0], 64) for _ in range(200)]
        target = (90 / 255) ** 2.2 * OutputStage.firmware_scale(255, 64)
        self.assertAlmostEqual(sum(levels) / len(levels), target, delta=0.05)
        self.assertLessEqual(max(levels) - min(levels), 1)


class FxTests(unittest.TestCase):
    def test_linear_round_trip_and_oklab_midpoint(self):
        for value in range(256):
            self.assertEqual(fx.from_linear(fx.to_linear((value, value, value))), (value, value, value))
        middle = fx.oklab_mix((255, 0, 0), (0, 255, 0), .5)
        self.assertGreater(min(middle[:2]), 100)  # no muddy brown/grey
        self.assertEqual(fx.oklab_mix((10, 20, 30), (200, 100, 0), 0), (10, 20, 30))

    def test_subpixel_dot_conserves_energy(self):
        canvas = fx.FxCanvas()
        canvas.dot(10.3, 4.6, (1, 1, 1), 1)
        self.assertAlmostEqual(sum(canvas.r), 1.0)
        lit = [i for i, v in enumerate(canvas.r) if v > 0]
        self.assertEqual(len(lit), 4)

    def test_easing_endpoints(self):
        for ease in fx.EASINGS.values():
            self.assertAlmostEqual(ease(0), 0, places=6)
            self.assertAlmostEqual(ease(1), 1, places=6)

    def test_proportional_text_width(self):
        self.assertEqual(fx.text_width('-5.2°'), 3 + 3 + 1 + 3 + 2 + 4)
        self.assertEqual(fx.text_width('1'), 2)


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.old = render_text_with_colors('12:34', base_color=(255, 150, 40))
        self.new = render_text_with_colors('WX 5C', base_color=(60, 190, 255))

    def test_every_effect_has_exact_endpoints_and_valid_frames(self):
        for effect in transitions.EFFECTS:
            with self.subTest(effect=effect):
                start = transitions.render(effect, *self.old, *self.new, 0)
                end = transitions.render(effect, *self.old, *self.new, 1)
                self.assertEqual(end, (self.new[0], self.new[1]))
                if effect != 'none':
                    self.assertEqual(start, (self.old[0], self.old[1]))
                for p in (.1, .33, .5, .77, .95):
                    frame, colors = transitions.render(effect, *self.old, *self.new, p)
                    self.assertEqual(len(frame), 8)
                    for row, crow in zip(frame, colors):
                        self.assertEqual(len(crow), 32)
                        for on, rgb in zip(row, crow):
                            self.assertEqual(bool(on), rgb is not None)
                            if rgb:
                                self.assertTrue(all(type(c) is int and 0 <= c <= 255 for c in rgb))

    def test_motion_is_gradual_not_eight_hard_steps(self):
        states = {repr(transitions.render('slide', *self.old, *self.new, i / 30)[1]) for i in range(31)}
        self.assertGreater(len(states), 20)

    def test_unknown_effect_falls_back_to_fade(self):
        self.assertEqual(transitions.render('sparkles', *self.old, *self.new, .5),
                         transitions.render('fade', *self.old, *self.new, .5))

    def test_transitions_fit_frame_budget(self):
        start = time.perf_counter()
        for effect in transitions.EFFECTS:
            for i in range(10):
                transitions.render(effect, *self.old, *self.new, i / 10)
        self.assertLess(time.perf_counter() - start, 3)


class AnimationTests(unittest.TestCase):
    def test_catalog_is_consistent(self):
        self.assertEqual(len(PRESETS), 15)
        for key, (title, description, palette) in PRESET_INFO.items():
            self.assertTrue(title and description)
            self.assertIn(palette, PALETTE_CHOICES)
        self.assertEqual(PALETTE_CHOICES[0], 'auto')

    def test_every_preset_moves_deterministically(self):
        async def check():
            for preset in sorted(PRESETS):
                with self.subTest(preset=preset):
                    first = await AnimationsModule().render({'preset': preset, '_elapsed': 3.0}, {})
                    again = await AnimationsModule().render({'preset': preset, '_elapsed': 3.0}, {})
                    later = await AnimationsModule().render({'preset': preset, '_elapsed': 3.4}, {})
                    self.assertEqual(first.color_frame, again.color_frame)
                    self.assertNotEqual(first.color_frame, later.color_frame)
                    self.assertTrue(any(any(row) for row in first.frame))
        asyncio.run(check())

    def test_game_of_life_survives_time_jumps(self):
        async def check():
            module = AnimationsModule()
            late = await module.render({'preset': 'game_of_life', '_elapsed': 25.0}, {})
            await module.render({'preset': 'game_of_life', '_elapsed': 2.0}, {})
            again = await module.render({'preset': 'game_of_life', '_elapsed': 25.0}, {})
            self.assertEqual(late.color_frame, again.color_frame)
        asyncio.run(check())

    def test_presets_fit_frame_budget(self):
        async def check():
            module = AnimationsModule()
            start = time.perf_counter()
            for preset in PRESETS:
                for i in range(10):
                    await module.render({'preset': preset, '_elapsed': i / 30}, {})
            return time.perf_counter() - start
        self.assertLess(asyncio.run(check()), 4)


class ClockRollTests(unittest.TestCase):
    def render(self, now):
        canvas = Canvas()
        canvas.clock(now)
        return canvas.colors

    def test_roll_runs_only_at_minute_start_and_settles(self):
        base = datetime(2026, 11, 7, 19, 59, 59, 900000)
        frames = [repr(self.render(base + timedelta(seconds=s))) for s in (.15, .3, .45, .6)]
        self.assertEqual(len(set(frames)), 4)
        settled = self.render(datetime(2026, 11, 7, 20, 0, 1, 500000))
        token = DIGIT_ROLL.set(False)
        try:
            plain = self.render(datetime(2026, 11, 7, 20, 0, 0, 100000))
        finally:
            DIGIT_ROLL.reset(token)
        digits = lambda colors: [[c is not None for c in row[6:25]] for row in colors]
        self.assertEqual(digits(settled), digits(plain))
        self.assertGreater(ROLL_SECONDS, .3)

    def test_unchanged_digits_never_move(self):
        now = datetime(2026, 11, 7, 12, 35, 0, 200000)
        rolling = self.render(now)
        token = DIGIT_ROLL.set(False)
        try:
            still = self.render(now)
        finally:
            DIGIT_ROLL.reset(token)
        for y in range(8):
            self.assertEqual(rolling[y][6:17], still[y][6:17])  # "12:3" stays put

    def test_colon_breathes_but_never_switches_off(self):
        levels = []
        for micro in range(0, 1_000_000, 100_000):
            colors = self.render(datetime(2026, 11, 7, 12, 34, 30, micro))
            levels.append(colors[2][15])
        self.assertTrue(all(levels))
        self.assertGreater(len(set(levels)), 3)


if __name__ == '__main__':
    unittest.main()
