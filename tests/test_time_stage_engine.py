from datetime import datetime, timedelta, timezone
import random
import unittest
from zoneinfo import ZoneInfo

from app.services.time_stage import EVENT_SCENES, NORMAL_SCENES
from app.services.time_stage.engine import TimeStageEngine, next_sleep_boundary


UTC = timezone.utc
NOW = datetime(2026, 10, 13, 12, 1, tzinfo=UTC)
KEYS = [scene.key for scene in NORMAL_SCENES]
EVENT = EVENT_SCENES[0].key


def config(**changes):
    result = dict(enabled=True, timezone='UTC', after_entries=2,
                  interval_seconds=60, duration_seconds=4, selection='ordered',
                  avoid_style_repeat=False, scenes=KEYS, weights={}, profile='all',
                  favorites=[], intensity='normal', color=None, minute_transition=True,
                  event_grace_seconds=60,
                  events={kind: dict(enabled=True, scenes=[EVENT], duration_seconds=6, panels=[])
                          for kind in ('hour', 'half', 'quarter', 'midnight')},
                  sleep=dict(enabled=False, start='02:00', end='08:00', brightness=1,
                             color='#ff500c', mode='auto', until=None))
    result.update(changes)
    return result


class TimeStageEngineTests(unittest.TestCase):
    def test_first_boundary_and_active_deadline(self):
        engine = TimeStageEngine(config())
        self.assertIsNone(engine.tick(NOW, 0, False))
        slot = engine.tick(NOW, 1, True)
        self.assertEqual(slot, dict(key=KEYS[0], start=1, end=5, kind='normal'))
        slot['end'] = 999
        self.assertEqual(engine.tick(NOW, 4, False)['end'], 5)
        self.assertIsNone(engine.tick(NOW, 5, False))
        self.assertIsNone(engine.tick(NOW, 6, True))

    def test_only_caller_regular_completions_count(self):
        engine = TimeStageEngine(config(interval_seconds=0))
        engine.tick(NOW, 0, True)
        self.assertIsNone(engine.tick(NOW, 5, True))  # priority content
        self.assertIsNone(engine.tick(NOW, 6, True, completed=True))
        self.assertEqual(engine.status(NOW, 6)['entries_remaining'], 1)
        self.assertEqual(engine.tick(NOW, 7, True, completed=True)['key'], KEYS[1])
        self.assertEqual(engine.last_completed, 0)

    def test_interval_is_monotonic_and_boundary_only(self):
        engine = TimeStageEngine(config(after_entries=0))
        engine.tick(NOW, 10, True)
        self.assertIsNone(engine.tick(NOW, 71, False))
        self.assertEqual(engine.tick(NOW, 72, True)['kind'], 'normal')

    def test_startup_and_wall_clock_jumps_never_replay_events(self):
        for start, end in [(datetime(2026, 10, 13, 12, tzinfo=UTC), None),
                           (NOW, NOW + timedelta(hours=1)),
                           (NOW, NOW - timedelta(minutes=1))]:
            engine = TimeStageEngine(config(after_entries=0, interval_seconds=0))
            self.assertEqual(engine.tick(start, 0, True)['kind'], 'normal')
            if end:
                self.assertIsNone(engine.tick(end, 5, True))

    def test_forward_crossing_waits_for_content_and_satisfies_clock_count(self):
        before = NOW.replace(minute=29, second=59)
        engine = TimeStageEngine(config())
        engine.tick(before, 0, True)
        self.assertIsNone(engine.tick(before + timedelta(seconds=10), 10, False, completed=True))
        slot = engine.tick(before + timedelta(seconds=20), 20, True, completed=True)
        self.assertEqual(slot['kind'], 'event')
        self.assertEqual(engine.last_completed, 0)
        self.assertIsNone(engine.tick(before + timedelta(seconds=27), 27, True))

    def test_grace_expires_during_long_content_and_queue_keeps_latest(self):
        before = NOW.replace(minute=29, second=59)
        engine = TimeStageEngine(config(after_entries=0, interval_seconds=0,
                                        event_grace_seconds=10))
        engine.tick(before, 0, True)
        engine.tick(before + timedelta(seconds=2), 5, False)
        self.assertIsNone(engine.tick(before + timedelta(seconds=12), 15, True))
        engine = TimeStageEngine(config(event_grace_seconds=600))
        engine.tick(before, 0, False)
        for seconds in range(60, 961, 60):
            engine.tick(before + timedelta(seconds=seconds), seconds, False)
        self.assertEqual(engine._pending[1], 'quarter')
        self.assertEqual(engine.tick(before + timedelta(seconds=962), 962, True)['kind'], 'event')

    def test_midnight_replaces_hour_only_when_enabled(self):
        before = datetime(2026, 10, 13, 23, 59, 59, tzinfo=UTC)
        for enabled, expected in [(True, 'midnight'), (False, 'hour')]:
            cfg = config()
            cfg['events']['midnight']['enabled'] = enabled
            engine = TimeStageEngine(cfg)
            engine.tick(before, 0, False)
            engine.tick(before + timedelta(seconds=1), 1, False)
            self.assertEqual(engine._pending[1], expected)

    def test_random_no_repeat_and_single_scene_never_starves(self):
        for keys in [KEYS, KEYS[:1]]:
            engine = TimeStageEngine(config(scenes=keys, selection='random',
                                            avoid_style_repeat=True), random.Random(42))
            slots = [engine.tick(NOW, i * 4, True, idle=True)['key'] for i in range(100)]
            if len(keys) > 1:
                self.assertTrue(all(a != b for a, b in zip(slots, slots[1:])))
            else:
                self.assertEqual(set(slots), set(keys))

    def test_ordered_profiles_and_config_are_detached(self):
        cfg = config(profile='favorites', favorites=KEYS[2:4])
        engine = TimeStageEngine(cfg)
        cfg['favorites'].clear()
        self.assertEqual([engine.tick(NOW, i * 4, True, idle=True)['key']
                          for i in range(4)], KEYS[2:4] * 2)
        engine.set_config(config(profile='retro'))
        self.assertTrue(engine.tick(NOW, 20, True, idle=True)['key'].startswith('retro_'))

    def test_idle_continuous_without_cadence_but_respects_disabled_stage(self):
        engine = TimeStageEngine(config(after_entries=0, interval_seconds=0))
        self.assertEqual(engine.tick(NOW, 0, True)['kind'], 'normal')
        self.assertEqual(engine.tick(NOW, 1, False, idle=True)['kind'], 'normal')
        self.assertEqual(engine.tick(NOW, 5, False, idle=True)['start'], 5)
        engine.set_config(config(enabled=False))
        self.assertIsNone(engine.tick(NOW, 10, False, idle=True))

    def test_sleep_blocks_everything_and_wake_does_not_replay(self):
        cfg = config()
        cfg['sleep'].update(enabled=True, start='12:00', end='12:31')
        engine = TimeStageEngine(cfg)
        before = NOW.replace(minute=29, second=59)
        self.assertIsNone(engine.tick(before, 0, True, idle=True))
        self.assertIsNone(engine.tick(before + timedelta(seconds=1), 1, True))
        self.assertEqual(engine.tick(before.replace(minute=31), 61, True)['kind'], 'normal')

    def test_manual_sleep_and_wake_expire_to_auto(self):
        for mode, active in [('sleep', True), ('wake', False)]:
            cfg = config()
            cfg['sleep'].update(enabled=True, start='12:00', end='13:00', mode=mode,
                                until=(NOW + timedelta(seconds=10)).isoformat())
            engine = TimeStageEngine(cfg)
            self.assertEqual(engine.sleep_state(NOW)['active'], active)
            state = engine.sleep_state(NOW + timedelta(seconds=10))
            self.assertEqual(state, dict(active=True, mode='auto', until=None, scheduled=True))

    def test_next_sleep_boundary_handles_dst_gap_fold_and_exact_boundary(self):
        cfg = config(timezone='Europe/Berlin')
        cfg['sleep'].update(start='02:30', end='08:00')
        zone = ZoneInfo(cfg['timezone'])
        gap = datetime(2026, 3, 29, 1, 59, tzinfo=zone)
        boundary = next_sleep_boundary(gap, cfg)
        self.assertEqual((boundary.hour, boundary.minute), (3, 30))
        first_fold = datetime(2026, 10, 25, 2, 45, tzinfo=zone, fold=0)
        boundary = next_sleep_boundary(first_fold, cfg)
        self.assertEqual((boundary.hour, boundary.minute), (8, 0))
        self.assertGreater(boundary.astimezone(UTC), first_fold.astimezone(UTC))
        self.assertEqual(next_sleep_boundary(boundary, cfg).hour, 2)
        cfg['sleep'].update(mode='sleep', until=boundary.isoformat())
        engine = TimeStageEngine(cfg)
        self.assertEqual(engine.sleep_state(first_fold)['mode'], 'sleep')
        self.assertEqual(engine.sleep_state(boundary)['mode'], 'auto')

    def test_implicit_manual_expiry_is_fixed_at_next_boundary(self):
        cfg = config()
        cfg['sleep'].update(mode='sleep')
        engine = TimeStageEngine(cfg)
        state = engine.sleep_state(NOW)
        self.assertEqual(state['until'], '2026-10-14T02:00:00+00:00')
        self.assertEqual(engine.sleep_state(datetime.fromisoformat(state['until']))['mode'], 'auto')

    def test_celestial_injection_and_empty_profile_status(self):
        cfg = config(profile='favorites')
        cfg['events']['sunrise'] = dict(enabled=True, duration_seconds=30, scenes=[], panels=[])
        engine = TimeStageEngine(cfg)
        self.assertTrue(engine.status(NOW, 0)['fallback'])
        self.assertEqual(engine.tick(NOW, 0, True)['key'], 'retro_cartridge')
        slot = engine.tick(NOW + timedelta(seconds=5), 5, True,
                            astronomy={'sunrise': NOW + timedelta(seconds=1)})
        self.assertEqual(slot, dict(key='sunrise', kind='celestial', start=5, end=35))

    def test_naive_time_rejected(self):
        with self.assertRaises(ValueError):
            TimeStageEngine(config()).tick(NOW.replace(tzinfo=None), 0, True)

    def test_ephemeris_event_list_is_consumed_at_content_boundary(self):
        cfg=config(after_entries=0,interval_seconds=0)
        cfg['events']['sunrise']=dict(enabled=True,scenes=['sunrise'],duration_seconds=45,panels=['time'])
        engine=TimeStageEngine(cfg)
        engine.tick(NOW,0,True)
        data={'events':[{'kind':'sunrise','at':(NOW+timedelta(seconds=5)).isoformat()}]}
        self.assertIsNone(engine.tick(NOW+timedelta(seconds=6),6,False,astronomy=data))
        slot=engine.tick(NOW+timedelta(seconds=10),10,True,astronomy=data)
        self.assertEqual(slot['kind'],'celestial');self.assertEqual(slot['key'],'sunrise')

    def test_fall_back_does_not_wake_in_the_repeated_hour(self):
        cfg=config(timezone='Europe/Vienna')
        cfg['sleep'].update(enabled=True,start='02:30',end='08:00')
        zone=ZoneInfo('Europe/Vienna');engine=TimeStageEngine(cfg)
        self.assertTrue(engine.sleep_state(datetime(2026,10,25,2,45,tzinfo=zone,fold=0))['active'])
        self.assertTrue(engine.sleep_state(datetime(2026,10,25,2,0,tzinfo=zone,fold=1))['active'])

    def test_first_hour_event_is_not_replayed_on_dst_fold(self):
        cfg=config(timezone='Europe/Vienna',after_entries=0,interval_seconds=0)
        engine=TimeStageEngine(cfg)
        start=datetime(2026,10,24,23,59,59,tzinfo=UTC)
        engine.tick(start,0,False)
        self.assertEqual(engine.tick(start+timedelta(seconds=1),1,True)['kind'],'event')
        for sec in range(60,3660,60):engine.tick(start+timedelta(seconds=sec),sec,False)
        self.assertIsNone(engine.tick(start+timedelta(seconds=3660),3660,True))
