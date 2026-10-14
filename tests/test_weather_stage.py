import os
import random
import time
import tracemalloc
import unittest
from collections import Counter

from app.services.weather_stage import (
    DEFAULTS, INFOS, STYLES, Director, Visit, catalog, condition_category,
    info_value, normalize, presentation_timing, render, story,
)


def cache(now=1000):
    return dict(weather_outdoor_temp=-5.2, weather_outdoor_updated_at=now,
                weather_code=61, weather_is_day=1, weather_precipitation=2.5,
                weather_wind_speed=12, weather_indoor_temp=21.5,
                weather_indoor_humidity=48, dht_updated_at=now)


class WeatherStageTests(unittest.TestCase):
    def test_catalog_defaults_and_independent_copies(self):
        result = catalog()
        self.assertEqual([s['key'] for s in result['styles']], ['home', 'station', 'nature', 'neon'])
        self.assertEqual([i['key'] for i in result['infos']], list(INFOS))
        self.assertEqual(result['defaults'], DEFAULTS)
        result['defaults']['weather_infos'].clear()
        self.assertEqual(normalize({})['weather_infos'], list(INFOS))

    def test_normalization_invalid_settings_preserves_unknown(self):
        settings = normalize(dict(weather_infos=['outside', [], 'outside', 'bad'], weather_styles={},
                                  weather_max_infos=99, weather_read_seconds='nan',
                                  weather_info_order='random', weather_style_order=None,
                                  weather_intensity=[], weather_comfort_min=100,
                                  weather_comfort_max=-100, custom={'keep': True}))
        self.assertEqual(settings['weather_infos'], ['outside'])
        self.assertEqual(settings['weather_styles'], list(STYLES))
        self.assertEqual(settings['weather_max_infos'], 4)
        self.assertEqual(settings['weather_read_seconds'], 4)
        self.assertEqual(settings['weather_info_order'], 'ordered')
        self.assertEqual(settings['weather_style_order'], 'ordered')
        self.assertEqual(settings['weather_intensity'], 'normal')
        self.assertEqual((settings['weather_comfort_min'], settings['weather_comfort_max']), (5, 35))
        self.assertEqual(settings['custom'], {'keep': True})
        for invalid in (None, 'bad', float('nan'), float('inf'), True):
            result = normalize({'weather_comfort_min': invalid, 'weather_comfort_max': invalid})
            self.assertEqual((result['weather_comfort_min'], result['weather_comfort_max']), (19, 25))
        self.assertEqual(normalize({'weather_read_seconds': 50})['weather_read_seconds'], 10)
        self.assertEqual(normalize({'weather_max_infos': -1})['weather_max_infos'], 1)

    def test_legacy_selection_only_without_explicit_infos(self):
        legacy = dict(show_outdoor=False, show_indoor=True, show_humidity=False)
        self.assertEqual(normalize(legacy)['weather_infos'], ['inside', 'conditions'])
        self.assertEqual(normalize({**legacy, 'weather_infos': ['outside']})['weather_infos'], ['outside'])
        self.assertEqual(normalize(dict(show_outdoor=False, show_indoor=False,
                                        show_humidity=False))['weather_infos'], ['conditions'])

    def test_fair_rotation_ordered_and_shuffle_no_extra_peers(self):
        for mode in ('ordered', 'shuffle'):
            for maximum in range(1, 5):
                director = Director(random.Random(maximum))
                values, styles = [], []
                for _ in range(100):
                    visit = director.begin(dict(weather_max_infos=maximum, weather_info_order=mode,
                                                weather_style_order=mode), cache(), 1000)
                    keys = [i['key'] for i in visit.infos]
                    self.assertEqual(len(keys), len(set(keys)))
                    self.assertLessEqual(len(keys), maximum)
                    values.extend(keys); styles.append(visit.style)
                counts = Counter(values)
                self.assertEqual(set(counts), set(INFOS))
                self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
                self.assertEqual(Counter(styles), Counter({key: 25 for key in STYLES}))
        director = Director()
        first = director.begin({}, cache(), 1000)
        second = director.begin({}, cache(), 1000)
        self.assertEqual([i['key'] for i in first.infos + second.infos], list(INFOS))

    def test_preview_freezes_data_and_does_not_consume_rotation(self):
        settings, data = {}, cache()
        director = Director()
        for _ in range(5): director.begin(settings, data, 1000, preview=True)
        visit = director.begin(settings, data, 1000)
        self.assertEqual(visit.style, 'home')
        self.assertEqual([i['key'] for i in visit.infos], ['outside', 'inside'])
        data['weather_outdoor_temp'] = 50
        self.assertEqual(visit.infos[0]['value'], '-5.2C')
        settings['weather_styles'] = ['neon']
        self.assertEqual(visit.settings['weather_styles'], list(STYLES))
        changed = director.begin({'weather_infos': ['humidity']}, data, 1000)
        self.assertEqual([i['key'] for i in changed.infos], ['humidity'])

    def test_source_specific_freshness_and_no_aggregate_fallback(self):
        settings = normalize({})
        data = cache(1000)
        self.assertEqual(info_value('outside', data, settings, 1100.9)['age_seconds'], 100)
        for key in INFOS: self.assertEqual(info_value(key, data, settings, 1000)['state'], 'fresh')
        for key in ('outside', 'conditions'):
            self.assertEqual(info_value(key, data, settings, 1900)['state'], 'fresh')
            self.assertEqual(info_value(key, data, settings, 1901)['state'], 'stale')
        for key in ('inside', 'humidity'):
            self.assertEqual(info_value(key, data, settings, 1300)['state'], 'fresh')
            self.assertEqual(info_value(key, data, settings, 1301)['state'], 'stale')
        data['dht_error'] = 'sensor offline'
        self.assertEqual(info_value('inside', data, settings, 1000)['state'], 'stale')
        self.assertEqual(info_value('outside', data, settings, 1000)['state'], 'fresh')
        data['weather_outdoor_error'] = 'offline'
        self.assertEqual(info_value('conditions', data, settings, 1000)['state'], 'stale')
        data.pop('weather_outdoor_updated_at'); data.pop('dht_updated_at')
        data.update(weather_updated_at=1000, updated_at=1000)
        for key in INFOS:
            info = info_value(key, data, settings, 1000)
            self.assertEqual(info['state'], 'stale')
            self.assertIsNone(info['age_seconds'])
        self.assertEqual(info_value('outside', cache(2000), settings, 1000)['state'], 'stale')

    def test_numeric_validation_negative_temperatures_and_real_trends(self):
        settings = normalize({})
        self.assertEqual(info_value('outside', cache(), settings, 1000)['value'], '-5.2C')
        for key, field, bad_values in (
            ('outside', 'weather_outdoor_temp', (True, float('nan'), float('inf'), 'bad', -101, 101)),
            ('humidity', 'weather_indoor_humidity', (True, -1, 101, float('nan'), None)),
        ):
            for bad in bad_values:
                data = cache(); data[field] = bad
                self.assertEqual(info_value(key, data, settings, 1000)['state'], 'missing')
        for humidity in (0, 100):
            data = cache(); data['weather_indoor_humidity'] = humidity
            self.assertEqual(info_value('humidity', data, settings, 1000)['value'], f'{humidity}%')
        self.assertIsNone(info_value('outside', cache(), settings, 1000)['trend'])
        for trend in (-1, 0, 1, True, 2, 'up'):
            data = cache(); data['weather_outdoor_temp_trend'] = trend
            expected = None if isinstance(trend, bool) or trend not in (-1, 0, 1) else trend
            self.assertEqual(info_value('outside', data, settings, 1000)['trend'], expected)

    def test_wmo_categories_day_night_and_unknown_weather(self):
        groups = {'clear': [0], 'cloudy': [1, 2, 3], 'fog': [45, 48],
                  'rain': [51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82],
                  'snow': [71, 73, 75, 77, 85, 86], 'storm': [95, 96, 99]}
        for category, codes in groups.items():
            for code in codes: self.assertEqual(condition_category(code), category)
        for bad in (None, True, -1, 4, 52, 72, 98, 100, 61.5, 'bad'):
            self.assertEqual(condition_category(bad), 'unknown')
        for day, value in ((True, 'SONNE'), (1, 'SONNE'), (False, 'MOND'),
                           (0, 'MOND'), (None, 'KLAR'), ('0', 'KLAR'), (2, 'KLAR')):
            data = cache(); data.update(weather_code=0, weather_is_day=day)
            self.assertEqual(info_value('conditions', data, {}, 1000)['value'], value)
        data = cache(); data['weather_code'] = None
        info = info_value('conditions', data, {}, 1000)
        self.assertEqual((info['value'], info['state'], info['category']), ('--', 'missing', 'unknown'))
        self.assertEqual(info_value('outside', data, {}, 1000)['state'], 'fresh')

    def test_all_sixteen_pairs_are_valid_deterministic_and_distinct(self):
        frames = []
        for style in STYLES:
            for key in INFOS:
                visit = Director().begin({'weather_styles': [style], 'weather_infos': [key]}, cache(), 1000)
                frames.append(repr(render(visit, 2).color_frame))
                sequence = []
                for elapsed in (.2, 1, 2, 3.3, 4.5, 7.9, visit.duration, visit.duration + 20):
                    result = render(visit, elapsed)
                    self.assertEqual(result, render(visit, elapsed))
                    self.assertEqual(result.scene_key, f'weather:{style}:{key}')
                    self.assertEqual(len(result.frame), 8)
                    for row in result.color_frame:
                        self.assertEqual(len(row), 32)
                        for rgb in row:
                            if rgb: self.assertTrue(all(type(c) is int and 0 <= c <= 255 for c in rgb))
                    sequence.append(repr(result.color_frame))
                self.assertGreater(len(set(sequence)), 2)
        self.assertEqual(len(set(frames)), 16)

    def test_read_is_still_full_length_with_badges_then_art_only(self):
        for style in STYLES:
            for state in ('fresh', 'stale', 'missing'):
                for seconds in (2, 4, 10):
                    data = {} if state == 'missing' else cache(0 if state == 'stale' else 1000)
                    visit = Director().begin(dict(weather_styles=[style], weather_read_seconds=seconds,
                                                  weather_infos=['outside', 'humidity']), data, 1000)
                    for index, info in enumerate(visit.infos):
                        start = .8 + index * visit.segment
                        first = render(visit, start + 2.901)
                        last = render(visit, start + 2.9 + seconds - .001)
                        self.assertEqual(first.color_frame, last.color_frame)
                        badge = (255, 65, 20) if state == 'stale' else (150, 150, 150) if state == 'missing' else None
                        self.assertEqual(last.color_frame[0][0], badge)
                        for phase in (2.9 + seconds + .2, visit.segment - .1):
                            elapsed = start + phase
                            actual_phase = elapsed - .8 - index * visit.segment
                            self.assertEqual(render(visit, elapsed).color_frame,
                                             story(style, actual_phase, info, 'normal').colors)
                    self.assertEqual(render(visit, visit.duration - .3).color_frame,
                                     story(style, visit.segment + .3, visit.infos[-1], 'normal').colors)

    def test_timing_caps_selection_ignores_playlist_and_extends_scroll(self):
        for count in range(1, 5):
            settings = dict(weather_max_infos=count, weather_read_seconds=4, duration_seconds=999)
            timing = presentation_timing(settings)
            visit = Director().begin(settings, cache(), 1000, preview=True)
            self.assertEqual(timing, dict(duration=.8 + count * 8 + .6, info_count=count,
                                          read_seconds=4.0, automatic=True))
            self.assertEqual(timing['duration'], visit.duration)
        timing = presentation_timing({'weather_infos': ['conditions'], 'weather_stage': False})
        self.assertEqual(timing['info_count'], 1)
        self.assertFalse(timing['automatic'])
        visit = Visit('home', [dict(key='conditions', label='WETTER', value='LANGER WETTERTEXT',
                                   state='fresh', category='unknown', is_day=None)], normalize({'weather_read_seconds': 2}))
        self.assertGreater(visit.read_seconds, 7)
        self.assertAlmostEqual(visit.duration, .8 + 4 + visit.read_seconds + .6)

    def test_missing_data_and_known_condition_art_are_coherent(self):
        for style in STYLES:
            for key in INFOS:
                visit = Director().begin(dict(weather_styles=[style], weather_infos=[key]), {}, 1000)
                self.assertEqual(visit.infos[0]['state'], 'missing')
                self.assertEqual(visit.infos[0]['value'], '--')
                self.assertIsNone(visit.infos[0]['is_day'])
                self.assertTrue(any(any(row) for row in render(visit, 2).frame))
            scenes = []
            for code, day in ((0, 1), (0, 0), (0, None), (3, 1), (61, 1), (73, 1), (45, 1), (95, 1), (None, None)):
                data = cache(); data.update(weather_code=code, weather_is_day=day)
                info = info_value('conditions', data, {}, 1000)
                scenes.append(repr(story(style, 1.5, info).colors))
            self.assertEqual(len(set(scenes)), len(scenes))

    @unittest.skipUnless(os.getenv('WEATHER_STAGE_METRICS'), 'optional local performance metrics')
    def test_bounded_memory_and_frame_speed(self):
        visit = Director().begin({'weather_max_infos': 4}, cache(), 1000)
        tracemalloc.start()
        start = time.perf_counter()
        for i in range(1000): render(visit, (i / 30) % visit.duration)
        elapsed = time.perf_counter() - start
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        print(f'weather: {elapsed * 1000 / 1000:.2f} ms/frame; retained={current}; peak={peak}')
        self.assertLess(current, 100_000)
        self.assertLess(peak, 300_000)
        self.assertLess(elapsed, 10)
