"""Pure 32x8 celestial ceremonies: a small landscape, a journey, then facts."""

from datetime import datetime
import math

from app.modules.base import ModulePayload
from .core import Canvas, event_progress, mix, shade


KEYS = ('sunrise', 'sunset', 'moonrise', 'moonset', 'golden_hour',
        'solar_noon', 'full_moon', 'new_moon', 'equinox', 'solstice')
PANELS = ('time', 'day_length', 'day_delta', 'next_event', 'phase',
          'illumination', 'next_full', 'twilight', 'night_length', 'moon_above')
_SUN_PANELS = ('time', 'day_length', 'day_delta', 'next_event', 'twilight')
_MOON_PANELS = ('time', 'phase', 'illumination', 'next_event', 'next_full', 'moon_above')


def _number(info, key):
    value = info.get(key)
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _stamp(value, date=False):
    try:
        at = datetime.fromisoformat(value)
        return at.strftime('%d.%m %H:%M' if date else '%H:%M')
    except (TypeError, ValueError):
        return '--:--'


def _minutes(value):
    if value is None:
        return '--'
    minutes = max(0, round(value))
    return f'{minutes // 60}H {minutes % 60:02d}M'


def _card(panel, kind, now, info):
    moon = kind in ('moonrise', 'moonset', 'full_moon', 'new_moon')
    if panel == 'time':
        return now.strftime('%H:%M')
    if panel == 'day_length':
        return 'TAG ' + _minutes(_number(info, 'day_length_minutes'))
    if panel == 'night_length':
        return 'NACHT ' + _minutes(_number(info, 'night_length_minutes'))
    if panel == 'day_delta':
        value = _number(info, 'day_delta_minutes')
        return 'TAG --' if value is None else f'TAG {value:+.1f}M'
    if panel == 'phase':
        return str(info.get('moon_phase') or 'PHASE --')
    if panel == 'illumination':
        value = _number(info, 'moon_illumination')
        return 'LICHT --' if value is None else f'LICHT {value:.0f}%'
    if panel == 'next_full':
        return 'VOLL ' + _stamp(info.get('next_full_moon'), date=True)
    if panel == 'moon_above':
        return 'MOND ' + _minutes(_number(info, 'moon_above_minutes'))
    if panel == 'twilight':
        field = 'civil_dawn' if kind == 'sunrise' else 'civil_dusk'
        return 'DAEMM ' + _stamp(info.get(field))
    if panel == 'next_event':
        field = ('moon' if moon else 'sun') + ('set' if kind.endswith('rise') else 'rise')
        value = info.get('next_' + field)
        try:
            another_day = datetime.fromisoformat(value).date() != now.date()
        except (TypeError, ValueError):
            another_day = False
        return ('UNTER ' if field.endswith('set') else 'AUF ') + _stamp(value, date=another_day)
    return '--'


def _scroll(canvas, text, age, color, span):
    # Pixel steps with a readable leading hold; work stays bounded
    # by visible glyphs, even if external metadata supplies a very long string.
    text = text.upper().replace('Ä', 'AE').replace('Ö', 'OE').replace('Ü', 'UE').replace('ß', 'SS')[:160]
    width = len(text) * 4 - 1
    if width <= 32:
        left = (32 - width) // 2
        for index, char in enumerate(text):
            if char == '+':
                canvas.bitmap(('000', '010', '111', '010', '000'), left + index * 4, 1, color)
            else:
                canvas.text(char, left + index * 4, 1, color)
        return
    speed = max(8, (width - 32) / max(.5, span - 1.2))
    offset = min(width - 32, max(0, int((age - .7) * speed)))
    first = max(0, (offset - 3) // 4)
    for index in range(first, min(len(text), first + 10)):
        if text[index] == '+':
            canvas.bitmap(('000', '010', '111', '010', '000'), index * 4 - offset, 1, color)
        else:
            canvas.text(text[index], index * 4 - offset, 1, color)


def _moon(canvas, cx, cy, radius, illumination, waxing, color):
    """Orthographic sphere with a curved terminator, not a cut-out rectangle."""
    fraction = max(0, min(1, illumination / 100))
    cosine = 1 - 2 * fraction
    for y in range(8):
        dy = (y - cy) / radius
        for x in range(max(0, int(cx - radius)), min(32, int(cx + radius) + 2)):
            dx = (x - cx) / radius
            if dx * dx + dy * dy > 1:
                continue
            edge = math.sqrt(max(0, 1 - dy * dy))
            lit = dx >= cosine * edge if waxing else dx <= -cosine * edge
            canvas.pixel(x, y, shade(color, .95 if lit else .10))


def _story(canvas, kind, now, age, span, info, color):
    phase = event_progress(age, span)
    moon = kind in ('moonrise', 'moonset', 'full_moon', 'new_moon')
    setting = kind in ('sunset', 'moonset')
    travel = min(1, max(0, (phase - .15) / .65))
    height = 6 - 5 * travel if not setting else 1 + 5 * travel
    if kind in ('full_moon', 'new_moon', 'solar_noon', 'equinox', 'solstice'):
        height = 2.8 + math.sin(phase * math.tau) * .6
    for y in range(8):
        for x in range(32):
            sky = (8, 14, 35) if moon else mix((8, 15, 40), (120, 49, 18), 1 - height / 8)
            canvas.pixel(x, y, shade(sky, .35 + (7 - y) * .07))
    for index, (x, y) in enumerate(((2, 1), (8, 0), (25, 1), (29, 3), (5, 3))):
        if moon or height > 3:
            canvas.pixel(x, y, shade((135, 163, 213), .3 + .3 * (1 + math.sin(age * .6 + index))))
    cx = 15.5 + math.sin(travel * math.pi) * 3
    if moon:
        illumination = _number(info, 'moon_illumination')
        waxing = info.get('moon_waxing')
        phase_name = str(info.get('moon_phase', ''))
        if not isinstance(waxing, bool):
            if phase_name.startswith(('Zunehm', 'Erstes')):
                waxing = True
            elif phase_name.startswith(('Abnehm', 'Letztes')):
                waxing = False
            elif illumination is not None and (illumination <= 1 or illumination >= 99):
                waxing = True  # At full/new the terminator direction is immaterial.
            else:
                illumination = None
        if illumination is None:
            # Unknown phase is explicitly a question mark, never a fake moon.
            canvas.bitmap(('110', '001', '010', '000', '010'), round(cx) - 1, round(height) - 2, color)
        else:
            if kind == 'moonrise':
                illumination *= min(1.0, phase / .3)
            _moon(canvas, cx, height, 2.6, illumination, waxing, color)
    else:
        for y in range(8):
            for x in range(12, 23):
                distance = math.hypot(x - cx, y - height)
                if distance <= 2:
                    canvas.pixel(x, y, mix((255, 112, 30), (255, 234, 129), 1 - distance / 3))
                elif distance < 3.4 and (x + y) % 2 == 0:
                    canvas.pixel(x, y, shade(color, .3))
    # Foreground silhouettes conceal a rising/setting disk at the horizon.
    for x in range(32):
        ridge = 6 + int((x // 5) % 3 == 0)
        for y in range(ridge, 8):
            canvas.pixel(x, y, (5, 16, 21) if moon else (29, 19, 17))
    if phase > .65:
        # A second scene: reflection/constellation expands across the horizon.
        for x in range(32):
            if (x + int(age * 3)) % 4 == 0:
                canvas.pixel(x, 7, shade(color, .35))
        if kind == 'sunrise':
            # Birds cross the brightening sky after the disk clears the ridge.
            for bird in range(2):
                x = int(age * 2 + bird * 13) % 38 - 3
                y = 1 + bird * 2
                canvas.pixel(x, y, color)
                wing = -1 if int(age * 3) % 2 else 1
                canvas.pixel(x - 1, y + wing, shade(color, .6))
                canvas.pixel(x + 1, y + wing, shade(color, .6))
        elif kind == 'sunset':
            # Evening windows light up in the foreground, one by one.
            for house in range(6):
                x = 2 + house * 5
                canvas.pixel(x, 5, (24, 21, 31))
                canvas.pixel(x + 1, 5, shade(color, .7 if phase > .65 + house * .025 else .1))
        elif moon:
            for x in range(1, 32, 5):
                canvas.pixel(x, 0 if x % 2 else 6, shade(color, .5))
    if kind == 'equinox':
        # Equal luminous and shaded arcs meet at the centre of the frame.
        for x in range(32):
            canvas.pixel(x, 0, shade(color if x < 16 else (99, 141, 240), .6))
    elif kind == 'solstice':
        for x in range(32):
            y = round(3 - 3 * math.sin(x / 31 * math.pi))
            canvas.pixel(x, y, shade(color, .45))
    elif kind == 'golden_hour':
        for x in range(32):
            if (x + int(age * 2)) % 5 == 0:
                canvas.pixel(x, 6, (240, 124, 30))
    # Brief clock interludes keep the time readable without covering all art.
    if .36 <= phase <= .48 or phase >= .86:
        for y in range(1, 6):
            for x in range(5, 26):
                canvas.colors[y][x] = None
        canvas.clock(now, color)


def render_celestial(kind, now, elapsed, duration=45, info=None, panels=None) -> ModulePayload:
    """Render a deterministic ceremony; default story spans about 25 seconds.

    Remaining time cycles selected, relevant fact cards. Unknown facts are
    visibly unavailable. Inputs are never mutated; there is no IO or scheduling.
    """
    if kind not in KEYS:
        raise ValueError('unknown celestial ceremony')
    if not math.isfinite(elapsed) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('elapsed and duration must be finite; duration must be positive')
    elapsed = max(0, min(float(elapsed), float(duration)))
    info = info or {}
    lunar = kind in ('moonrise', 'moonset', 'full_moon', 'new_moon')
    relevant = _MOON_PANELS if lunar else _SUN_PANELS + ('night_length',)
    selected = relevant if panels is None else tuple(p for p in panels if p in relevant)
    if not selected:
        selected = ('time',)
    canvas = Canvas()
    color = (170, 202, 255) if lunar else (255, 190, 78)
    story_span = duration * .55
    if elapsed < story_span:
        _story(canvas, kind, now, elapsed, story_span, info, color)
    elif elapsed >= duration:
        canvas.clock(now, color)
    else:
        card_span = (duration - story_span) / len(selected)
        position = elapsed - story_span
        index = min(len(selected) - 1, int(position / card_span))
        _scroll(canvas, _card(selected[index], kind, now, info), position - index * card_span, color, card_span)
        for x in range(32):
            canvas.pixel(x, 7, shade(color, .12 if x >= int(elapsed / duration * 32) else .45))
    return canvas.payload(now, kind)
