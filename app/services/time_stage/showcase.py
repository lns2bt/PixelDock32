"""Five showcase clocks: pendulum, live sky, nixie tubes, weather and aquarium.

All motion is driven by wall time (never by visit age), drawn with sub-pixel
helpers, and keeps the HH:MM digits unobstructed. The sky and weather clocks
read optional context (astronomy, current weather) set by the display service;
without it they fall back to calm, honest defaults.
"""

from contextvars import ContextVar
from datetime import datetime, timedelta
import math

from app.services.rendering import FONT_3X5

from .core import Canvas, Scene, mix, progress, seconds, shade

# {'astronomy': {...}, 'weather': {'category': str, 'is_day': bool | None}}
SCENE_CONTEXT = ContextVar('scene_context', default={})

SILVER = (205, 215, 235)
WARM_WHITE = (255, 238, 205)
NIXIE = (255, 122, 34)


def _wall(now):
    """Continuous wall-clock seconds within the day (pure, wraps at midnight)."""
    return now.hour * 3600 + now.minute * 60 + seconds(now)


def _hash(*values):
    from app.services.fx import hash01
    return hash01(*values)


# --------------------------------------------------------------------------- #
# Newton's cradle
# --------------------------------------------------------------------------- #

def _pendulum(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    t = seconds(now)
    canvas.clock(now, WARM_WHITE, x=0)
    pivots = (23.0, 26.0, 29.0)
    length = 4.4
    for x in range(21, 32):
        canvas.pixel(x, 0, shade(SILVER, .45))
    # One click per second: the left ball swings out on even seconds,
    # the right ball on odd seconds; the middle ball stays still.
    phase = t % 1
    swing = math.sin(math.pi * phase) * .55
    left_turn = int(t) % 2 == 0
    for index, px in enumerate(pivots):
        angle = 0.0
        if index == 0 and left_turn:
            angle = -swing
        elif index == len(pivots) - 1 and not left_turn:
            angle = swing
        bx = px + length * math.sin(angle)
        by = .5 + length * math.cos(angle)
        for step in range(1, 8):
            f = step / 8
            canvas.dot(px + (bx - px) * f, .5 + (by - .5) * f, shade(SILVER, .45))
        # Solid ball: a 2 × 2 sub-pixel core with a soft rim.
        canvas.glow(bx, by, 1.9, shade(SILVER, .8), .9)
        canvas.dot(bx - .5, by - .5, SILVER, 1.0)
        canvas.dot(bx + .5, by + .5, shade(SILVER, .85), 1.0)
        canvas.dot(bx - .6, by - .7, (255, 255, 255), .9)
    # A tiny spark where the balls touch, right at the full second.
    click = max(0.0, 1 - phase / .12) + max(0.0, (phase - .88) / .12)
    if click > 0:
        canvas.glow(24.5 if left_turn else 27.5, 4.9, .9, (255, 225, 150), .8 * min(1.0, click))
    for x in range(21, 32):
        canvas.pixel(x, 7, shade(SILVER, .15))
    return canvas


# --------------------------------------------------------------------------- #
# Live sky
# --------------------------------------------------------------------------- #

def _local(value, now, fallback):
    """ISO timestamp → naive local time in ``now``'s zone (or the fallback)."""
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if parsed is None:
        return fallback
    if parsed.tzinfo is not None and now.tzinfo is not None:
        parsed = parsed.astimezone(now.tzinfo)
    return parsed.replace(tzinfo=None)


def _sky_times(now):
    astro = SCENE_CONTEXT.get().get('astronomy') or {}
    local = now.replace(tzinfo=None)
    day = local.replace(hour=0, minute=0, second=0, microsecond=0)
    sunrise = _local(astro.get('sunrise'), now, day + timedelta(hours=7))
    sunset = _local(astro.get('sunset'), now, day + timedelta(hours=17))
    dawn = _local(astro.get('civil_dawn'), now, sunrise - timedelta(minutes=35))
    dusk = _local(astro.get('civil_dusk'), now, sunset + timedelta(minutes=35))
    if not dawn <= sunrise < sunset <= dusk:
        dawn, sunrise = day + timedelta(hours=6, minutes=25), day + timedelta(hours=7)
        sunset, dusk = day + timedelta(hours=17), day + timedelta(hours=17, minutes=35)
    return dawn, sunrise, sunset, dusk, local


SKY = {
    'night': ((2, 3, 14), (6, 9, 30)),
    'twilight': ((30, 18, 70), (230, 95, 70)),
    'golden': ((60, 90, 170), (255, 150, 60)),
    'day': ((25, 80, 175), (110, 170, 230)),
}


def _sky(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    dawn, sunrise, sunset, dusk, local = _sky_times(now)

    def frac(a, b):
        span = (b - a).total_seconds()
        return max(0.0, min(1.0, (local - a).total_seconds() / span)) if span > 0 else 0.0

    if sunrise <= local <= sunset:
        day = frac(sunrise, sunset)
        edge = min(day, 1 - day)
        golden = max(0.0, 1 - edge / .12)
        top = mix(SKY['day'][0], SKY['golden'][0], golden)
        low = mix(SKY['day'][1], SKY['golden'][1], golden)
        body = ('sun', 1.5 + day * 29, 6.6 - 5.4 * math.sin(math.pi * day))
    elif dawn <= local < sunrise or sunset < local <= dusk:
        amount = frac(dawn, sunrise) if local < sunrise else 1 - frac(sunset, dusk)
        top = mix(SKY['night'][0], SKY['twilight'][0], amount)
        low = mix(SKY['night'][1], SKY['twilight'][1], amount)
        body = ('sun', 1.5 if local < sunrise else 30.5, 7.4 - amount * .8)
    else:
        top, low = SKY['night']
        body = ('moon', None, None)
    level = .38
    for y in range(8):
        tint = mix(top, low, y / 7)
        for x in range(32):
            canvas.pixel(x, y, shade(tint, level))
    if body[0] == 'sun':
        canvas.glow(body[1], body[2], 2.2, (255, 220, 120), .9)
        canvas.glow(body[1], body[2], .9, (255, 250, 220), 1.0)
    else:
        t = _wall(now)
        for star in range(14):
            x, y = int(_hash(star, 81) * 32), int(_hash(star, 82) * 6)
            twinkle = .25 + .35 * (.5 + .5 * math.sin(t * (.7 + _hash(star, 83)) + star))
            canvas.blend(x, y, (210, 220, 255), twinkle)
        night_span = 24 * 3600 - (dusk - dawn).total_seconds()
        since_dusk = (local - dusk).total_seconds() % (24 * 3600)
        f = max(0.0, min(1.0, since_dusk / night_span)) if night_span > 0 else .5
        canvas.glow(2 + f * 28, 5.5 - 4 * math.sin(math.pi * f), 1.3, (235, 235, 205), .85)
    # Dark hills; at night a few warm windows.
    for x in range(32):
        hill = 6.4 + .7 * math.sin(x * .42) + .4 * math.sin(x * 1.3)
        for y in range(8):
            if y >= hill:
                canvas.pixel(x, y, shade(low, .12) if body[0] == 'sun' else (4, 5, 10))
    if body[0] == 'moon':
        for x in (4, 13, 27):
            canvas.pixel(x, 7, (120, 80, 25))
    # Quiet backing keeps the digits legible against bright skies.
    for y in range(1, 6):
        for x in range(6, 25):
            color = canvas.colors[y][x] or (0, 0, 0)
            canvas.pixel(x, y, shade(color, .3))
    canvas.clock(now, (255, 248, 235))
    return canvas


# --------------------------------------------------------------------------- #
# Nixie tubes
# --------------------------------------------------------------------------- #

def _nixie(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    tubes = (3, 9, 18, 24)
    for x0 in tubes:
        for y in range(7):
            canvas.pixel(x0, y, (18, 14, 16))
            canvas.pixel(x0 + 4, y, (18, 14, 16))
        for x in range(x0 + 1, x0 + 4):
            canvas.pixel(x, 0, (26, 20, 22) if x % 2 else (14, 11, 12))
        # Stacked cathodes: the unlit "8" glimmers faintly behind each digit.
        canvas.bitmap(FONT_3X5['8'], x0 + 1, 1, (34, 14, 6))
        for x in range(x0, x0 + 5):
            canvas.pixel(x, 7, (40, 26, 14) if x in (x0 + 1, x0 + 3) else (12, 9, 8))
    canvas.ticker(now, '%H:%M', 0, 1, NIXIE, positions=(4, 10, 14, 19, 25))
    # Orange halo around lit cathode strokes (gas glow).
    lit = [(x, y) for y in range(1, 6) for x in range(32)
           if canvas.colors[y][x] and canvas.colors[y][x][0] > 150]
    flicker = .9 + .1 * math.sin(_wall(now) * 23)
    for x, y in lit:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            canvas.blend(x + dx, y + dy, (120, 45, 10), .45 * flicker)
    for x, y in lit:
        canvas.pixel(x, y, shade(NIXIE, flicker))
    # A small neon indicator lamp ticks the seconds above the colon.
    pulse = math.exp(-((seconds(now) % 1) / .25))
    canvas.glow(15, 0, .9, (255, 90, 40), .25 + .6 * pulse)
    return canvas


# --------------------------------------------------------------------------- #
# Weather clock
# --------------------------------------------------------------------------- #

def _weather_clock(now: datetime, elapsed: float) -> Canvas:
    from app.services import fx
    from app.services.weather_stage import _weather_layer

    info = SCENE_CONTEXT.get().get('weather') or {}
    category = info.get('category', 'unknown')
    is_day = info.get('is_day')
    layer = fx.FxCanvas()
    _weather_layer(layer, category, is_day, _wall(now) % 3600, 'home')
    layer.fade(.55)
    canvas = Canvas()
    canvas.colors = layer.to_colors()
    for y in range(1, 6):
        for x in range(6, 25):
            color = canvas.colors[y][x] or (0, 0, 0)
            canvas.pixel(x, y, shade(color, .25))
    canvas.clock(now, (235, 245, 255))
    progress(canvas, now, (90, 150, 220), y=7)
    return canvas


# --------------------------------------------------------------------------- #
# Aquarium
# --------------------------------------------------------------------------- #

def _aquarium(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    t = _wall(now)
    for y in range(8):
        for x in range(32):
            canvas.pixel(x, y, mix((2, 10, 30), (4, 30, 60), y / 7))
    for x in range(32):
        canvas.pixel(x, 7, (60, 50, 25) if x % 3 else (85, 70, 35))
    # Swaying seaweed at the edges.
    for base in (1, 4, 27, 30):
        for y in range(3, 7):
            sway = .6 * math.sin(t * 1.3 + base + y * .9) * (6 - y) / 3
            canvas.dot(base + sway, y, (40, 150, 70), .8)
    canvas.clock(now, (190, 240, 255), x=6, y=0)
    # Two fish patrol the lane below the digits, in opposite directions.
    for index, (speed, color) in enumerate(((2.1, (255, 140, 40)), (1.6, (255, 220, 90)))):
        travel = (t * speed + index * 17) % 40
        x = travel - 5 if index == 0 else 36 - travel
        sprite = ('110', '111') if index == 0 else ('011', '111')
        canvas.sprite(sprite, x, 5 + .4 * math.sin(t * 2 + index), color, .95)
    # One bubble per second rises past the clock on each side.
    for side, x0 in enumerate((2.5, 28.5)):
        for k in range(3):
            age = (seconds(now) + k + side * .5) % 3 / 3
            canvas.dot(x0 + .5 * math.sin(age * 9 + side), 6 - age * 6.5, (170, 220, 255), .7 * (1 - age))
    return canvas


SCENES = [
    Scene(key='show_pendulum', title="Newton's Cradle", style='Showcase · Physics',
          description='A silver cradle clicks beside a warm clock; balls swing on sub-pixel arcs.',
          seconds='One ball swings out and clicks back every second, alternating left and right.',
          render=_pendulum, digit_style='roll', added='0.5.0'),
    Scene(key='show_sky', title='Live Sky', style='Showcase · Sky',
          description='The real sky for your location: sun arc by day, dawn and dusk colours, moon and stars at night.',
          seconds='Sun and moon positions follow the actual time; stars twinkle continuously.',
          render=_sky, digit_style='fade', added='0.5.0'),
    Scene(key='show_nixie', title='Nixie Tubes', style='Showcase · Vintage',
          description='Four glowing orange gas tubes with faint stacked cathodes and a neon seconds lamp.',
          seconds='The neon lamp above the colon pulses once per second; digits cycle like real cathodes.',
          render=_nixie, digit_style='decode', added='0.5.0'),
    Scene(key='show_weather', title='Weather Clock', style='Showcase · Weather',
          description='The clock above the current outdoor weather: sun, clouds, rain, snow, fog or storm.',
          seconds='The bottom bar fills over the minute; the weather animates continuously.',
          render=_weather_clock, digit_style='drop', added='0.5.0'),
    Scene(key='show_aquarium', title='Aquarium', style='Showcase · Water',
          description='Fish patrol below the clock between swaying seaweed and a sandy floor.',
          seconds='A bubble rises on each side every second.',
          render=_aquarium, digit_style='morph', added='0.5.0'),
]
