"""Pure Time-Stage scheduling: wall time for policy, monotonic time for slots.

Only the caller knows which playlist entries are regular: pass ``completed``
for those entries only. No rendering, persistence or hardware lives here.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import random
from zoneinfo import ZoneInfo

from . import EVENT_SCENES, NORMAL_SCENES


UTC = timezone.utc
_NORMAL = {scene.key: scene for scene in NORMAL_SCENES}
_EVENT = {scene.key: scene for scene in EVENT_SCENES}


def _aware(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Time-Stage requires timezone-aware timestamps')
    return value.astimezone(UTC)


def _zone(config):
    return ZoneInfo(config.get('timezone', 'UTC'))


def _minute(value):
    hour, minute = map(int, value.split(':'))
    return hour * 60 + minute


def _local_boundary(date, value, zone, ending=False):
    naive = datetime.combine(date, datetime.min.time()) + timedelta(minutes=_minute(value))
    valid = []
    for fold in (0, 1):
        utc = naive.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if utc.astimezone(zone).replace(tzinfo=None) == naive:
            valid.append(utc)
    if valid:
        return max(valid) if ending else min(valid)
    return max(naive.replace(tzinfo=zone, fold=f).astimezone(UTC) for f in (0,1))


def next_sleep_boundary(now, config):
    """Next strictly future start/end, including both folds of repeated times.

    Nonexistent local times roll forward by the DST gap. Comparing in UTC is
    essential: datetime comparisons in the same ZoneInfo ignore ``fold``.
    """
    instant = _aware(now)
    zone = _zone(config)
    local = instant.astimezone(zone)
    sleep = config.get('sleep', {})
    candidates = []
    for day in range(3):
        date = (local + timedelta(days=day)).date()
        for value in (sleep.get('start', '02:00'), sleep.get('end', '08:00')):
            minute = _minute(value)
            naive = datetime.combine(date, datetime.min.time()) + timedelta(minutes=minute)
            resolved = [_local_boundary(date, value, zone, ending=value == sleep.get('end', '08:00'))]
            candidates.extend(value for value in resolved if value > instant)
    return min(candidates).astimezone(zone)


class TimeStageEngine:
    def __init__(self, config, rng=None):
        self.rng = rng if rng is not None else random.Random()
        self.active = None
        self.last_completed = 0
        self._last_clock = None
        self._observed = None
        self._pending = None
        self._last_key = None
        self._ordered_last = {}
        self._started = False
        self._event_seen = {}
        self.set_config(config)

    def set_config(self, config):
        self.config = deepcopy(config)
        self.zone = _zone(config)
        self._pending = None
        if not config.get('enabled', False):
            self.active = None

    def sleep_state(self, now):
        instant = _aware(now)
        local = instant.astimezone(self.zone)
        sleep = self.config.get('sleep', {})
        start = _minute(sleep.get('start', '02:00'))
        end = _minute(sleep.get('end', '08:00'))
        scheduled = False
        if sleep.get('enabled', False):
            for offset in (-1, 0):
                date = local.date() + timedelta(days=offset)
                begin = _local_boundary(date, sleep.get('start', '02:00'), self.zone)
                finish_date = date + timedelta(days=int(start >= end))
                finish = _local_boundary(finish_date, sleep.get('end', '08:00'), self.zone, ending=True)
                scheduled |= begin <= instant < finish
        mode = sleep.get('mode', 'auto')
        until = sleep.get('until')
        # Missing expiry is resolved once, not recomputed at each tick.
        if mode != 'auto' and until is None:
            until = next_sleep_boundary(now, self.config).isoformat()
            sleep['until'] = until
        if mode != 'auto' and until is not None and _aware(until) <= instant:
            mode, until = 'auto', None
            sleep.update(mode='auto', until=None)
        return {'active': mode == 'sleep' if mode != 'auto' else scheduled,
                'mode': mode, 'until': until if mode != 'auto' else None,
                'scheduled': scheduled}

    def _normal_keys(self):
        keys = [key for key in self.config.get('scenes', list(_NORMAL)) if key in _NORMAL]
        profile = self.config.get('profile', 'all')
        if profile == 'retro':
            keys = [key for key in keys if key.startswith('retro_')]
        elif profile == 'calm':
            keys = [key for key in keys if key.startswith('craft_') or key in
                    ('chroma_lava', 'chroma_prism', 'retro_cartridge')]
        elif profile == 'favorites':
            keys = [key for key in keys if key in self.config.get('favorites', [])]
        return list(dict.fromkeys(keys))

    def _select(self, keys, group):
        if not keys:
            return None
        if self.config.get('selection', 'ordered') == 'ordered':
            previous = self._ordered_last.get(group)
            index = (keys.index(previous) + 1) % len(keys) if previous in keys else 0
            key = keys[index]
            self._ordered_last[group] = key
            return key
        choices = [key for key in keys if key != self._last_key] or keys
        if self.config.get('avoid_style_repeat', False) and self._last_key:
            # Catalog styles are descriptive; prefixes represent broad families.
            family = self._last_key.rsplit('_', 1)[0] if self._last_key.startswith('event_') else self._last_key.split('_')[0]
            varied = [key for key in choices if not key.startswith(family + '_')]
            choices = varied or choices
        weights = self.config.get('weights', {})
        return self.rng.choices(choices, weights=[weights.get(key, 1) for key in choices], k=1)[0]

    def _observe(self, now, astronomy):
        previous, self._observed = self._observed, now
        if previous is None or not 0 <= (now - previous).total_seconds() <= 120:
            self._pending = None
            return
        events = self.config.get('events', {})
        candidates = []
        # UTC minute walking handles skipped/repeated local minutes naturally.
        cursor = previous.replace(second=0, microsecond=0) + timedelta(minutes=1)
        while cursor <= now:
            local = cursor.astimezone(self.zone)
            kind = None
            if local.minute == 0:
                kind = 'midnight' if local.hour == 0 and events.get('midnight', {}).get('enabled') else 'hour'
            elif local.minute == 30:
                kind = 'half'
            elif local.minute in (15, 45):
                kind = 'quarter'
            if kind and events.get(kind, {}).get('enabled', False):
                candidates.append((cursor, kind, 'event'))
            cursor += timedelta(minutes=1)
        # Real ephemeris data supplies today's event list; maps remain useful in tests.
        sky = astronomy or {}
        entries = ((item['kind'], item.get('at')) for item in sky['events']) if isinstance(sky.get('events'), list) else sky.items()
        for kind, value in entries:
            if not events.get(kind, {}).get('enabled', False):
                continue
            if isinstance(value, dict):
                value = value.get('at', value.get('time'))
            if value is None:
                continue
            at = _aware(value)
            if previous < at <= now:
                candidates.append((at, kind, 'celestial'))
        fresh = []
        for at, kind, source in candidates:
            # A repeated local hour during DST is celebrated only once.
            identity = (kind, at.astimezone(self.zone).strftime('%Y-%m-%dT%H:%M'))
            if identity not in self._event_seen:
                self._event_seen[identity] = at
                fresh.append((at, kind, source))
        self._event_seen = {key: at for key, at in self._event_seen.items() if (now - at).total_seconds() < 172800}
        if fresh:
            self._pending = max(fresh, key=lambda item: item[0])
        if self._pending and (now - self._pending[0]).total_seconds() > self.config.get('event_grace_seconds', 60):
            self._pending = None

    def _begin(self, key, kind, duration, monotonic):
        self.active = {'key': key, 'start': monotonic,
                       'end': monotonic + duration, 'kind': kind}
        self.last_completed = 0
        self._last_clock = monotonic
        self._last_key = key
        self._started = True
        return dict(self.active)

    def tick(self, now, monotonic, boundary, completed=False, astronomy=None, idle=False):
        now = _aware(now)
        self._observe(now, astronomy)
        if self.sleep_state(now)['active']:
            self.active = None
            self._pending = None
            return None
        if not self.config.get('enabled', False):
            self.active = None
            self._pending = None
            return None
        if completed:
            self.last_completed += 1
        if self.active and monotonic < self.active['end']:
            return dict(self.active)
        just_finished = self.active is not None
        self.active = None
        if not (boundary or idle):
            return None
        if self._pending:
            _, category, kind = self._pending
            self._pending = None
            event = self.config['events'][category]
            keys = [key for key in event.get('scenes', []) if key in _EVENT]
            key = category if kind == 'celestial' else self._select(keys, category)
            if key:
                return self._begin(key, kind, event.get('duration_seconds', 30 if kind == 'celestial' else 8), monotonic)
        count = self.config.get('after_entries', 0)
        interval = self.config.get('interval_seconds', 0)
        due = (not self._started or idle or
               (count > 0 and self.last_completed >= count) or
               (interval > 0 and self._last_clock is not None and monotonic - self._last_clock >= interval))
        if due and (not just_finished or idle or completed):
            key = self._select(self._normal_keys() or ['retro_cartridge'], 'normal')
            if key:
                return self._begin(key, 'normal', self.config.get('duration_seconds', 8), monotonic)
        return None

    def status(self, now, monotonic):
        interval = self.config.get('interval_seconds', 0)
        count = self.config.get('after_entries', 0)
        sleep = self.sleep_state(now)
        if sleep['mode'] == 'auto' and self.config.get('sleep', {}).get('enabled'):
            sleep['until'] = next_sleep_boundary(now, self.config).isoformat()
        return {'enabled': self.config.get('enabled', False), 'sleep': sleep,
                'active': dict(self.active) if self.active and monotonic < self.active['end'] else None,
                'next_clock_seconds': (max(0, interval - (monotonic - self._last_clock))
                                       if interval and self._last_clock is not None else (0 if not self._started else None)),
                'entries_remaining': max(0, count - self.last_completed) if count else None,
                'fallback': not bool(self._normal_keys()),
                'error': 'No eligible Time-Stage scenes' if not self._normal_keys() else None}
