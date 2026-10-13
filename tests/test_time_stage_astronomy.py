from datetime import datetime, timedelta, timezone
import json
import time
import unittest
from zoneinfo import ZoneInfo

from app.services.time_stage.astronomy import calculate
from app.services.time_stage.celestial import KEYS, render_celestial, _card, _moon
from app.services.time_stage.core import Canvas


VIENNA = ZoneInfo('Europe/Vienna')


class AstronomyTests(unittest.TestCase):
    def calculate(self, month=6, day=21, hour=12):
        return calculate(datetime(2026, month, day, hour, tzinfo=VIENNA), 48.2082, 16.3738)

    def assert_clock_near(self, value, hour, minute, tolerance=3):
        at = datetime.fromisoformat(value)
        self.assertLess(abs(at.hour * 60 + at.minute + at.second / 60 - hour * 60 - minute), tolerance)

    def test_vienna_2026_summer_and_winter_accuracy_anchors(self):
        # Vienna's published summer/winter solstice times, rounded to minutes;
        # modest tolerance allows standard refraction / observer convention.
        summer = self.calculate()
        self.assert_clock_near(summer['sunrise'], 4, 54)
        self.assert_clock_near(summer['sunset'], 20, 59)
        self.assert_clock_near(summer['civil_dawn'], 4, 12)
        self.assert_clock_near(summer['civil_dusk'], 21, 40)
        self.assert_clock_near(summer['solar_noon'], 12, 56)
        self.assertAlmostEqual(summer['day_length_minutes'], 965.5, delta=3)
        winter = self.calculate(12, 21)
        self.assert_clock_near(winter['sunrise'], 7, 42)
        self.assert_clock_near(winter['sunset'], 16, 3)
        self.assertAlmostEqual(winter['day_length_minutes'], 501.3, delta=3)
        self.assertIn('solstice', [e['kind'] for e in summer['events']])
        self.assertIn('solstice', [e['kind'] for e in winter['events']])

    def test_lunar_accuracy_phase_and_real_visibility(self):
        info = self.calculate()
        self.assert_clock_near(info['moonrise'], 12, 31, tolerance=5)
        self.assert_clock_near(info['moonset'], 0, 26, tolerance=5)
        self.assertAlmostEqual(info['moon_illumination'], 45.2, delta=1)
        self.assertTrue(info['moon_waxing'])
        full = datetime.fromisoformat(info['next_full_moon'])
        self.assertEqual(full.date().isoformat(), '2026-06-30')
        self.assert_clock_near(info['next_full_moon'], 1, 57)
        # Moonset precedes moonrise; visibility includes both sides of midnight.
        self.assertAlmostEqual(info['moon_above_minutes'], 715.5, delta=3)
        self.assertGreater(info['moon_above_minutes'], 0)

    def test_dst_days_use_actual_boundaries_not_fixed_24_hours(self):
        for month, day, total in ((3, 29, 1380), (10, 25, 1500)):
            info = self.calculate(month, day)
            self.assertAlmostEqual(info['day_length_minutes'] + info['day_dark_minutes'], total)
            sunrise = datetime.fromisoformat(info['sunrise'])
            sunset = datetime.fromisoformat(info['sunset'])
            expected = (sunset.astimezone(timezone.utc) - sunrise.astimezone(timezone.utc)).total_seconds() / 60
            self.assertAlmostEqual(info['day_length_minutes'], expected, places=5)
            self.assertLess(abs(info['day_delta_minutes']), 5)
            self.assertGreaterEqual(info['moon_above_minutes'], 0)
            self.assertLessEqual(info['moon_above_minutes'], total)

    def test_polar_events_absent_not_fabricated(self):
        for month, daylight in ((6, 1440), (12, 0)):
            now = datetime(2026, month, 21, 12, tzinfo=ZoneInfo('Arctic/Longyearbyen'))
            info = calculate(now, 78.2232, 15.6469)
            for field in ('sunrise', 'sunset', 'next_sunrise', 'next_sunset'):
                self.assertIsNone(info[field])
            self.assertIsNone(info['civil_dawn'])
            self.assertIsNone(info['civil_dusk'])
            self.assertFalse(any(e['kind'] in ('sunrise', 'sunset') for e in info['events']))
            self.assertAlmostEqual(info['day_length_minutes'], daylight, places=4)

    def test_events_are_today_next_events_are_future_and_json_safe(self):
        for month, day in ((6, 21), (3, 20), (6, 30), (7, 14), (10, 25)):
            now = datetime(2026, month, day, 23, 59, tzinfo=VIENNA)
            info = calculate(now, 48.2082, 16.3738)
            json.dumps(info, allow_nan=False)
            self.assertEqual(info['date'], now.strftime('%Y%m%d'))
            for event in info['events']:
                at = datetime.fromisoformat(event['at'])
                self.assertIsNotNone(at.utcoffset())
                self.assertEqual(at.astimezone(VIENNA).date(), now.date())
                self.assertIn(event['kind'], KEYS)
            for key, value in info.items():
                if key.startswith('next_') and value is not None:
                    self.assertGreater(datetime.fromisoformat(value), now)
            self.assertEqual(info, calculate(now, 48.2082, 16.3738))
        self.assertIn('equinox', [e['kind'] for e in self.calculate(3, 20)['events']])
        self.assertIn('full_moon', [e['kind'] for e in self.calculate(6, 30)['events']])
        self.assertIn('new_moon', [e['kind'] for e in self.calculate(7, 14)['events']])

    def test_validation(self):
        with self.assertRaises(ValueError):
            calculate(datetime(2026, 1, 1), 48, 16)
        now = datetime(2026, 1, 1, tzinfo=VIENNA)
        for lat, lon in ((91, 16), (48, -181), (float('nan'), 16), (48, float('inf'))):
            with self.assertRaises(ValueError):
                calculate(now, lat, lon)


class CelestialTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 6, 21, 12, 34, 29, tzinfo=VIENNA)
        self.info = calculate(self.now, 48.2082, 16.3738)

    def test_all_ceremonies_are_deterministic_bounded_and_animate(self):
        for kind in KEYS:
            frames = []
            for elapsed in (-1, 0, 3, 8, 15, 22, 26, 30, 35, 40, 45, 1000):
                with self.subTest(kind=kind, elapsed=elapsed):
                    result = render_celestial(kind, self.now, elapsed, info=self.info)
                    self.assertEqual(result, render_celestial(kind, self.now, elapsed, info=self.info))
                    self.assertEqual(result.text, '12:34')
                    self.assertEqual(result.scene_key, kind)
                    self.assertEqual(len(result.frame), 8)
                    self.assertEqual(len(result.color_frame), 8)
                    for bits, row in zip(result.frame, result.color_frame):
                        self.assertEqual(len(row), 32)
                        for bit, color in zip(bits, row):
                            self.assertEqual(bit, int(color is not None))
                            if color:
                                self.assertEqual(len(color), 3)
                                self.assertTrue(all(type(c) is int and 0 <= c <= 255 for c in color))
                    frames.append(repr(result.color_frame))
            self.assertGreater(len(set(frames)), 5, kind)
            expected = Canvas()
            expected.clock(self.now)
            final = render_celestial(kind, self.now, 45)
            for y in range(8):
                for x in range(32):
                    if expected.colors[y][x]:
                        self.assertIsNotNone(final.color_frame[y][x])

    def test_unknown_facts_are_not_fabricated_and_panels_are_selective(self):
        for panel in ('day_length', 'day_delta', 'next_event', 'phase', 'illumination', 'next_full', 'twilight', 'night_length', 'moon_above'):
            self.assertIn('--', _card(panel, 'moonrise', self.now, {}))
        before = json.dumps(self.info, sort_keys=True)
        time_only = render_celestial('sunrise', self.now, 35, panels=['time'], info=self.info)
        filtered = render_celestial('sunrise', self.now, 35, panels=['phase'], info=self.info)
        self.assertEqual(time_only, filtered)
        self.assertEqual(before, json.dumps(self.info, sort_keys=True))
        self.assertNotEqual(render_celestial('moonrise', self.now, 3).color_frame,
                            render_celestial('moonrise', self.now, 3, info=self.info).color_frame)

    def test_curved_moon_phase_and_waxing_orientation(self):
        amounts = []
        for illumination in (0, 25, 50, 75, 100):
            canvas = Canvas()
            _moon(canvas, 15.5, 3.5, 3, illumination, True, (200, 200, 200))
            amounts.append(sum(color == (190, 190, 190) for row in canvas.colors for color in row))
        self.assertEqual(amounts, sorted(amounts))
        self.assertGreater(len(set(amounts)), 3)
        waxing, waning = Canvas(), Canvas()
        _moon(waxing, 15.5, 3.5, 3, 25, True, (200, 200, 200))
        _moon(waning, 15.5, 3.5, 3, 25, False, (200, 200, 200))
        self.assertEqual(waxing.colors, [list(reversed(row)) for row in waning.colors])
        self.assertNotEqual(waxing.colors, waning.colors)

    def test_long_cards_scroll_and_duration_is_scalable(self):
        a = render_celestial('moonrise', self.now, 27, info=self.info, panels=['phase'])
        b = render_celestial('moonrise', self.now, 31, info=self.info, panels=['phase'])
        self.assertNotEqual(a.color_frame, b.color_frame)
        for duration in (30, 45, 60):
            result = render_celestial('sunrise', self.now + timedelta(minutes=1), duration, duration=duration)
            self.assertEqual(result.text, '12:35')

    def test_validation_and_small_render_budget(self):
        for value in (float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                render_celestial('sunrise', self.now, value)
            with self.assertRaises(ValueError):
                render_celestial('sunrise', self.now, 0, duration=value)
        with self.assertRaises(ValueError):
            render_celestial('invalid', self.now, 0)
        with self.assertRaises(ValueError):
            render_celestial('sunrise', self.now, 0, duration=0)
        start = time.perf_counter()
        for i in range(60):
            for kind in KEYS:
                render_celestial(kind, self.now, i / 2, info=self.info)
        self.assertLess(time.perf_counter() - start, 5)
