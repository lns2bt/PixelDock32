"""Offline astronomical ephemerides, expressed in the caller's civil timezone.

Rise/set uses PyEphem's apparent upper limb at sea level (standard atmospheric
refraction). Civil twilight uses the solar centre at -6 degrees, without
refraction. No cache, network access, or scheduler lives in this module.
"""

from datetime import datetime, time, timedelta, timezone
import math

import ephem


UTC = timezone.utc


def _date(value):
    return ephem.Date(value.astimezone(UTC).replace(tzinfo=None))


def _local(value, tz):
    return value.datetime().replace(tzinfo=UTC).astimezone(tz)


def _observer(latitude, longitude, at, horizon='0', pressure=1010):
    observer = ephem.Observer()
    observer.lat, observer.lon = str(latitude), str(longitude)
    observer.elevation = 0
    observer.pressure = pressure
    observer.horizon = horizon
    observer.date = _date(at)
    return observer


def _crossings(observer, body, start, end, rising, center=False):
    """All crossings in a half-open UTC interval (including 25-hour days)."""
    method = observer.next_rising if rising else observer.next_setting
    cursor = start.astimezone(UTC) - timedelta(microseconds=1)
    result = []
    # A civil day has at most two crossings of either kind; a bounded guard
    # protects against numerical boundary repeats without truncating DST days.
    for _ in range(4):
        observer.date = _date(cursor)
        try:
            at = _local(method(body, use_center=center), UTC)
        except (ephem.AlwaysUpError, ephem.NeverUpError):
            break
        if at >= end.astimezone(UTC):
            break
        if at >= start.astimezone(UTC):
            result.append(at)
        cursor = at + timedelta(seconds=1)
    return result


def _next(observer, body, now, rising):
    observer.date = _date(now)
    try:
        value = (observer.next_rising if rising else observer.next_setting)(body)
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        return None
    return _local(value, now.tzinfo).isoformat()


def _above_minutes(observer, body, start, end, rises, sets):
    """Integrate visibility, including bodies already up at local midnight."""
    observer.date = _date(start)
    body.compute(observer)
    # PyEphem rise/set is an upper-limb event; altitude already includes
    # atmospheric refraction, and radius is the body's apparent semidiameter.
    above = float(body.alt) + float(body.radius) >= float(observer.horizon)
    cursor = start.astimezone(UTC)
    total = 0.0
    for at, state in sorted([(at, True) for at in rises] + [(at, False) for at in sets]):
        if above:
            total += (at - cursor).total_seconds()
        cursor, above = at, state
    if above:
        total += (end.astimezone(UTC) - cursor).total_seconds()
    return total / 60


def calculate(now: datetime, latitude: float, longitude: float) -> dict:
    """Return JSON-safe real events for *today*, and separately future events.

    ``moon_above_minutes`` is visibility within this actual local day, not the
    difference of two possibly unrelated moon crossings. Polar missing events
    remain None; visibility can legitimately be zero or the entire civil day.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('now must be timezone-aware')
    latitude, longitude = float(latitude), float(longitude)
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError('latitude must be between -90 and 90')
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError('longitude must be between -180 and 180')
    tz = now.tzinfo
    start = datetime.combine(now.date(), time.min, tzinfo=tz)
    end = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=tz)
    observer = _observer(latitude, longitude, start)
    sun, moon = ephem.Sun(), ephem.Moon()
    result = {'events': [], 'location': {'latitude': latitude, 'longitude': longitude},
              'date': now.strftime('%Y%m%d')}

    def record(kind, times):
        local = [at.astimezone(tz).isoformat() for at in times]
        result[kind] = local[0] if local else None
        result['events'].extend({'kind': kind, 'at': at} for at in local)

    crossings = {}
    for name, body in (('sun', sun), ('moon', moon)):
        rises = _crossings(observer, body, start, end, True)
        sets = _crossings(observer, body, start, end, False)
        crossings[name] = rises, sets
        record(name + 'rise', rises)
        record(name + 'set', sets)
        result['next_' + name + 'rise'] = _next(observer, body, now, True)
        result['next_' + name + 'set'] = _next(observer, body, now, False)

    twilight = _observer(latitude, longitude, start, '-6', 0)
    dawns = _crossings(twilight, sun, start, end, True, True)
    dusks = _crossings(twilight, sun, start, end, False, True)
    result['civil_dawn'] = dawns[0].astimezone(tz).isoformat() if dawns else None
    result['civil_dusk'] = dusks[0].astimezone(tz).isoformat() if dusks else None
    golden = _observer(latitude, longitude, start, '6', 0)
    golden_starts = dawns + _crossings(golden, sun, start, end, False, True)
    record('golden_hour', sorted(golden_starts))
    golden_ends = _crossings(golden, sun, start, end, True, True) + dusks
    result['golden_windows'] = [{'start': at.astimezone(tz).isoformat(),
                                'end': finish.astimezone(tz).isoformat()}
                               for at in sorted(golden_starts)
                               for finish in [next((candidate for candidate in sorted(golden_ends) if candidate > at), None)]
                               if finish is not None]

    observer.date = _date(start - timedelta(microseconds=1))
    noon = _local(observer.next_transit(sun), tz)
    record('solar_noon', [noon] if start <= noon < end else [])
    result['day_length_minutes'] = _above_minutes(observer, sun, start, end, *crossings['sun'])
    result['moon_above_minutes'] = _above_minutes(observer, moon, start, end, *crossings['moon'])
    previous = datetime.combine(now.date() - timedelta(days=1), time.min, tzinfo=tz)
    prev_rises = _crossings(observer, sun, previous, start, True)
    prev_sets = _crossings(observer, sun, previous, start, False)
    previous_length = _above_minutes(observer, sun, previous, start, prev_rises, prev_sets)
    result['day_delta_minutes'] = result['day_length_minutes'] - previous_length
    result['night_length_minutes'] = (end.astimezone(UTC) - start.astimezone(UTC)).total_seconds() / 60 - result['day_length_minutes']
    result['day_dark_minutes'] = result['night_length_minutes']
    if result['sunset']:
        setting = datetime.fromisoformat(result['sunset'])
        following = _next(observer, sun, setting + timedelta(seconds=1), True)
        if following:
            result['night_length_minutes'] = (datetime.fromisoformat(following).astimezone(UTC) - setting.astimezone(UTC)).total_seconds() / 60
    result['night_length_scope'] = 'Sonnenuntergang heute bis zum folgenden Sonnenaufgang; ohne Horizontwechsel dunkler Anteil des lokalen Tages'

    moon.compute(_date(now))
    illumination = float(moon.moon_phase) * 100
    waxing = ephem.previous_new_moon(_date(now)) > ephem.previous_full_moon(_date(now))
    if illumination < 1:
        phase = 'Neumond'
    elif illumination > 99:
        phase = 'Vollmond'
    elif 45 <= illumination <= 55:
        phase = 'Erstes Viertel' if waxing else 'Letztes Viertel'
    else:
        phase = 'Zunehmender Mond' if waxing else 'Abnehmender Mond'
    result.update(moon_illumination=illumination, moon_phase=phase, moon_waxing=bool(waxing))
    for kind, function in (('full_moon', ephem.next_full_moon), ('new_moon', ephem.next_new_moon),
                           ('equinox', ephem.next_equinox), ('solstice', ephem.next_solstice)):
        result['next_' + kind] = _local(function(_date(now)), tz).isoformat()
        at = _local(function(_date(start - timedelta(microseconds=1))), tz)
        if start <= at < end:
            result['events'].append({'kind': kind, 'at': at.isoformat()})
    result['events'].sort(key=lambda event: datetime.fromisoformat(event['at']).astimezone(UTC))
    return result
