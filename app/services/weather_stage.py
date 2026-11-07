"""Pure, bounded 32×8 weather stories; one coherent style per frozen visit."""
from copy import deepcopy
from dataclasses import dataclass
import math
import random
import time

from app.modules.base import ModulePayload
from app.services import fx
from app.services.bitcoin_stage import FairRotation
from app.services.time_stage.core import Canvas


STYLES = {
    'home': ('Pixel Home', 'From the weather outside the house to the warm room'),
    'station': ('Weather Station', 'Quiet instruments and measuring scales'),
    'nature': ('Nature World', 'Sky, forest and water without promises of health'),
    'neon': ('Neon Lab', 'Luminous measuring chambers and clear data'),
}
INFOS = {
    'outside': ('Outside temperature', 'OUTSIDE'),
    'inside': ('Indoor temperature', 'INSIDE'),
    'humidity': ('Humidity inside', 'HUMIDITY'),
    'conditions': ('Weather outside', 'WEATHER'),
}
DEFAULTS = dict(weather_stage=True, weather_styles=list(STYLES), weather_infos=list(INFOS),
                weather_max_infos=2, weather_read_seconds=4, weather_info_order='ordered',
                weather_style_order='ordered', weather_intensity='normal',
                weather_comfort_min=19, weather_comfort_max=25)
PALETTES = {
    'home': ((255, 192, 92), (110, 185, 220)),
    'station': ((130, 224, 200), (105, 150, 185)),
    'nature': ((155, 215, 105), (90, 180, 205)),
    'neon': ((230, 110, 255), (75, 220, 240)),
}
def number(value, low=-math.inf, high=math.inf):
    if isinstance(value, bool): return None
    try: value = float(value)
    except (TypeError, ValueError, OverflowError): return None
    return value if math.isfinite(value) and low <= value <= high else None


def normalize(settings):
    supplied = settings or {}
    result = {**DEFAULTS, **supplied}
    if 'weather_infos' not in supplied:
        result['weather_infos'] = [key for key in INFOS if key == 'conditions' or
                                  bool(supplied.get({'outside': 'show_outdoor', 'inside': 'show_indoor',
                                                    'humidity': 'show_humidity'}[key], True))]
    for key, allowed in (('weather_styles', STYLES), ('weather_infos', INFOS)):
        values = result[key]
        result[key] = list(dict.fromkeys(v for v in values if isinstance(v, str) and v in allowed)) if isinstance(values, list) else []
        if not result[key]: result[key] = list(allowed)
    for key, low, high in (('weather_max_infos', 1, 4), ('weather_read_seconds', 2, 10)):
        try: result[key] = max(low, min(high, int(result[key])))
        except (TypeError, ValueError, OverflowError): result[key] = DEFAULTS[key]
    for key in ('weather_info_order', 'weather_style_order'):
        if result[key] not in ('ordered', 'shuffle'): result[key] = 'ordered'
    if result['weather_intensity'] not in ('calm', 'normal', 'lively'): result['weather_intensity'] = 'normal'
    for key in ('weather_comfort_min', 'weather_comfort_max'):
        value = number(result[key])
        result[key] = max(5, min(35, value)) if value is not None else DEFAULTS[key]
    result['weather_comfort_min'], result['weather_comfort_max'] = sorted(
        (result['weather_comfort_min'], result['weather_comfort_max']))
    result['weather_stage'] = bool(result['weather_stage'])
    return result


def condition_category(code):
    code = number(code, 0, 99)
    if code is None or code != int(code): return 'unknown'
    if code == 0: return 'clear'
    if code in (1, 2, 3): return 'cloudy'
    if code in (45, 48): return 'fog'
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82): return 'rain'
    if code in (71, 73, 75, 77, 85, 86): return 'snow'
    if code in (95, 96, 99): return 'storm'
    return 'unknown'


def info_value(key, cache, settings, now=None):
    now = time.time() if now is None else now
    outdoor = key in ('outside', 'conditions')
    stamp = cache.get('weather_outdoor_updated_at' if outdoor else 'dht_updated_at')
    error = cache.get('weather_outdoor_error' if outdoor else 'dht_error')
    timestamp = number(stamp, 0)
    age = max(0, now - timestamp) if timestamp is not None else None
    category = condition_category(cache.get('weather_code'))
    day = cache.get('weather_is_day')
    is_day = bool(day) if isinstance(day, (bool, int, float)) and day in (0, 1) else None
    value = numeric = None
    if key in ('outside', 'inside'):
        numeric = number(cache.get('weather_outdoor_temp' if outdoor else 'weather_indoor_temp'), -90, 70)
        if numeric is not None: value = f'{numeric:.1f}'.rstrip('0').rstrip('.') + 'C'
    elif key == 'humidity':
        numeric = number(cache.get('weather_indoor_humidity'), 0, 100)
        if numeric is not None: value = f'{numeric:.1f}'.rstrip('0').rstrip('.') + '%'
    elif key == 'conditions' and category != 'unknown':
        # A clear sky with unknown day/night is not evidence of sunshine.
        value = {'clear': 'SUN' if is_day is True else 'MOON' if is_day is False else 'CLEAR',
                 'cloudy': 'CLOUDS', 'fog': 'FOG', 'rain': 'RAIN',
                 'snow': 'SNOW', 'storm': 'STORM'}[category]
    stale = value is not None and (bool(error) or age is None or
                                  age > (900 if outdoor else 300) or timestamp > now + 60)
    trend_key = {'outside': 'weather_outdoor_temp_trend', 'inside': 'weather_indoor_temp_trend',
                 'humidity': 'weather_indoor_humidity_trend', 'conditions': 'weather_conditions_trend'}[key]
    trend = cache.get(trend_key, cache.get({'outside': 'weather_outdoor_trend',
                                         'inside': 'weather_indoor_trend',
                                         'humidity': 'weather_humidity_trend',
                                         'conditions': 'weather_conditions_trend'}[key]))
    if isinstance(trend, bool) or not isinstance(trend, (int, float)) or trend not in (-1, 0, 1): trend = None
    if stale or value is None: trend = None
    return dict(key=key, title=INFOS[key][0], label=INFOS[key][1], value=value if value is not None else '--',
                state='missing' if value is None else 'stale' if stale else 'fresh',
                age_seconds=int(age) if age is not None else None,
                updated_at=stamp, numeric=numeric, trend=trend,
                category=category, is_day=is_day,
                precipitation=number(cache.get('weather_precipitation'), 0, 1000),
                wind_speed=number(cache.get('weather_wind_speed'), 0, 500))


@dataclass
class Visit:
    style: str
    infos: list
    settings: dict

    @property
    def read_seconds(self):
        scrolling = max(((len(info['value']) * 4 + 32) / 12 for info in self.infos
                         if len(info['value']) > 8), default=0)
        return max(self.settings['weather_read_seconds'], scrolling)

    @property
    def segment(self): return 4 + self.read_seconds

    @property
    def duration(self): return .8 + len(self.infos) * self.segment + .6


class Director:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.infos = FairRotation(self.rng)
        self.styles = FairRotation(self.rng)

    def begin(self, settings, cache, now=None, preview=False):
        settings = normalize(settings)
        if preview:
            keys = settings['weather_infos'][:settings['weather_max_infos']]
            style = settings['weather_styles'][0]
        else:
            keys = self.infos.take(settings['weather_infos'], settings['weather_max_infos'],
                                   'random' if settings['weather_info_order'] == 'shuffle' else 'ordered')
            style = self.styles.take(settings['weather_styles'], 1,
                                     'random' if settings['weather_style_order'] == 'shuffle' else 'ordered')[0]
        now = time.time() if now is None else now
        return Visit(style, [info_value(key, cache, settings, now) for key in keys], deepcopy(settings))


def presentation_timing(settings, cache=None, now=None):
    visit = Director().begin(settings, cache or {}, now, preview=True)
    return dict(duration=float(visit.duration), info_count=len(visit.infos),
                read_seconds=float(visit.read_seconds), automatic=visit.settings['weather_stage'])


# --------------------------------------------------------------------------- #
# Rendering: a full-width weather *scene*, then a clear *card*
# (animated icon left, colour-coded value right), then the scene again.
# --------------------------------------------------------------------------- #

SCENE_END = .9          # scene only
CARD_IN = 1.6           # scene → card (value rolls in)
CARD_EXTRA = .8         # extra reading time on top of weather_read_seconds
OUTRO = .6              # card → scene
VALUE_X = 10            # value column starts right of the 8 × 8 icon

CLOUD8 = ('00011000', '00111110', '01111111', '11111111', '01111110')
BOLT = ('0011', '0110', '1111', '0110', '0100')
HOUSE = ('00011000', '00111100', '01111110', '11111111')
DROP7 = ('0001000', '0011100', '0011100', '0111110', '1111111', '1111111', '1111111', '0111110')
THERMO = ('010', '101', '101', '101', '101', '111', '111')

TEMPERATURE_STOPS = ((-15, (120, 100, 255)), (0, (90, 200, 255)), (10, (70, 230, 170)),
                     (18, (160, 235, 70)), (24, (255, 210, 50)), (30, (255, 125, 40)), (36, (255, 55, 55)))
COMFORT = dict(cold=(110, 170, 255), ok=(120, 235, 140), warm=(255, 130, 95))
HUMIDITY = dict(dry=(255, 190, 90), ok=(110, 220, 255), humid=(90, 130, 255))
STALE = (255, 150, 40)
GREY = (145, 145, 150)
SUN_YELLOW, MOON_WHITE = (255, 205, 60), (235, 230, 200)
CLOUD_WHITE, CLOUD_DARK = (215, 222, 235), (110, 115, 135)
RAIN_BLUE, SNOW_WHITE, BOLT_YELLOW = (70, 150, 255), (235, 245, 255), (255, 225, 70)


def temperature_color(value):
    """Intuitive scale: violet/blue = freezing … green = mild … red = hot."""
    if value is None:
        return GREY
    if value <= TEMPERATURE_STOPS[0][0]:
        return TEMPERATURE_STOPS[0][1]
    for (low, a), (high, b) in zip(TEMPERATURE_STOPS, TEMPERATURE_STOPS[1:]):
        if value <= high:
            return fx.oklab_mix(a, b, (value - low) / (high - low))
    return TEMPERATURE_STOPS[-1][1]


def value_color(info, settings):
    numeric = info.get('numeric')
    if info['state'] == 'missing' or (numeric is None and info['key'] != 'conditions'):
        return GREY
    key = info['key']
    if key == 'outside':
        return temperature_color(numeric)
    if key == 'inside':
        if numeric < settings['weather_comfort_min']: return COMFORT['cold']
        if numeric > settings['weather_comfort_max']: return COMFORT['warm']
        return COMFORT['ok']
    if key == 'humidity':
        return HUMIDITY['dry'] if numeric < 30 else HUMIDITY['humid'] if numeric > 60 else HUMIDITY['ok']
    return {'clear': SUN_YELLOW if info.get('is_day') is not False else MOON_WHITE, 'cloudy': CLOUD_WHITE,
            'fog': (190, 200, 210), 'rain': (120, 185, 255), 'snow': SNOW_WHITE,
            'storm': BOLT_YELLOW}.get(info.get('category'), GREY)


def display_value(info, room):
    """Compact on-panel text: '-5.2°', '22°', '48%', 'RAIN', '--'."""
    numeric = info.get('numeric')
    if info['key'] in ('outside', 'inside') and numeric is not None:
        text = f'{numeric:.1f}'.rstrip('0').rstrip('.') + '°'
        if fx.text_width(text) > room:
            text = f'{round(numeric)}°'
        return text.replace('-0°', '0°')
    if info['key'] == 'humidity' and numeric is not None:
        return f'{round(numeric)}%'
    return info['value']


def icon_key(info):
    key = info['key']
    if key == 'inside': return 'house'
    if key == 'humidity': return 'drop'
    category = info.get('category', 'unknown')
    if category == 'clear':
        return 'sun' if info.get('is_day') is True else 'moon' if info.get('is_day') is False else 'clear'
    if category == 'unknown':
        return 'thermo' if key == 'outside' else 'unknown'
    return category


def _lin(color, amount=1.0):
    return fx.scale(fx.to_linear(color), amount)


def _cloud(canvas, x, y, color, alpha=1.0):
    canvas.bitmap(CLOUD8, x, y, _lin(color), alpha)
    # Soft top-light: clouds read as volumes, not flat blobs.
    canvas.bitmap(('00011000', '00110000'), x, y, _lin((255, 255, 255), .25), alpha * .5, mode='add')


def draw_icon(canvas, key, t, info, alpha=1.0, x0=0):
    """Animated 8 × 8 weather icons; gentle motion, no strobe."""
    stale = info.get('state') == 'stale'
    dim = .55 if stale else 1.0
    if key == 'sun':
        canvas.glow(x0 + 3.5, 3.5, 2.6, _lin(SUN_YELLOW, dim), alpha * 1.3)
        for ray in range(8):
            angle = ray * math.pi / 4 + t * .35
            pulse = .55 + .45 * math.sin(t * 2.2 + ray * (math.pi / 2))
            canvas.dot(x0 + 3.5 + math.cos(angle) * 3.4, 3.5 + math.sin(angle) * 3.4,
                       _lin(SUN_YELLOW, dim), alpha * pulse * .9)
    elif key == 'moon':
        for y in range(8):
            for x in range(8):
                body = 1 - fx.smoothstep(2.4, 3.2, math.hypot(x - 3.5, y - 3.5))
                bite = 1 - fx.smoothstep(2.0, 2.8, math.hypot(x - 5.3, y - 2.3))
                canvas.add(x0 + x, y, _lin(MOON_WHITE, dim), alpha * max(0.0, body - bite))
        for sx, sy, k in ((7, 0, 0), (6, 6, 1)):
            canvas.add(x0 + sx, sy, _lin((255, 255, 255)), alpha * (.25 + .25 * math.sin(t * 2 + k * 2)))
    elif key == 'clear':
        twinkle = .6 + .4 * math.sin(t * 1.5)
        canvas.glow(x0 + 3.5, 3.5, 1.2, _lin((200, 225, 255), dim), alpha * twinkle)
        for dx, dy in ((0, -3), (0, 3), (-3, 0), (3, 0)):
            canvas.line(x0 + 3.5, 3.5, x0 + 3.5 + dx * .9, 3.5 + dy * .9, _lin((170, 200, 255), dim), alpha * .5)
    elif key in ('cloudy', 'rain', 'snow', 'storm', 'unknown'):
        drift = .5 * math.sin(t * .8)
        if key == 'cloudy' and info.get('is_day') is True:
            canvas.glow(x0 + 5.5, 1.8, 1.8, _lin(SUN_YELLOW, dim), alpha)
        cloud = CLOUD_DARK if key == 'storm' else GREY if key == 'unknown' else CLOUD_WHITE
        _cloud(canvas, x0 + drift, 1 if key == 'cloudy' else 0, fx.oklab_mix((0, 0, 0), cloud, dim), alpha)
        if key == 'rain' or key == 'storm':
            for i, dx in enumerate((1.5, 4, 6.3)):
                y = 5 + ((t * 4.5 + i * .37 * 3) % 3.2)
                canvas.dot(x0 + dx + drift - (y - 5) * .25, y - .4, _lin(RAIN_BLUE, dim), alpha * .9)
        if key == 'snow':
            for i, dx in enumerate((1.2, 3.8, 6.2)):
                y = 5 + ((t * 1.4 + i * .9) % 3.2)
                canvas.dot(x0 + dx + .6 * math.sin(t * 2 + i), y - .3, _lin(SNOW_WHITE, dim), alpha * .9)
        if key == 'storm':
            glow = .55 + .45 * math.sin(t * 2.6) ** 2   # slow, soft — never a flash
            canvas.bitmap(BOLT, x0 + 2 + drift, 3, _lin(BOLT_YELLOW, dim * glow), alpha)
        if key == 'unknown':
            canvas.bitmap(('11', '01', '00', '01'), x0 + 3 + drift, 4, _lin(GREY), alpha * .8)
    elif key == 'fog':
        for i, y in enumerate((1.5, 3.5, 5.5)):
            shift = math.sin(t * .7 + i * 1.8) * 1.2
            for x in range(8):
                fade = .35 + .3 * math.sin(x * .9 + t + i)
                canvas.hline_soft(y, x0 + x + shift * .3, x0 + x + 1 + shift * .3, _lin((200, 210, 220), dim), alpha * fade)
    elif key == 'house':
        roof, wall = (230, 120, 70), (200, 170, 140)
        canvas.bitmap(HOUSE, x0, 0, _lin(roof, dim), alpha)
        for y in range(4, 8):
            canvas.over(x0 + 1, y, _lin(wall, dim), alpha)
            canvas.over(x0 + 6, y, _lin(wall, dim), alpha)
        for x in range(1, 7):
            canvas.over(x0 + x, 7, _lin(wall, dim), alpha)
        warmth = .7 + .3 * math.sin(t * 1.3)
        for wx, wy in ((3, 4), (4, 4), (3, 5), (4, 5)):
            canvas.over(x0 + wx, wy, _lin((255, 200, 90), dim * warmth), alpha)
    elif key == 'drop':
        level = (info.get('numeric') or 0) / 100
        surface = 8 - level * 7
        for y, row in enumerate(DROP7):
            for x, bit in enumerate(row):
                if bit != '1':
                    continue
                wave = .35 * math.sin(x * 1.3 + t * 2.5)
                filled = fx.smoothstep(surface + wave - .5, surface + wave + .5, y + .5)
                canvas.over(x0 + x, y, _lin(HUMIDITY['ok'], dim * (.16 + .84 * filled)), alpha)
    elif key == 'thermo':
        level = 0 if info.get('numeric') is None else fx.clamp01(((info.get('numeric') or 0) + 15) / 50)
        color = value_color(info, normalize({})) if info.get('numeric') is not None else GREY
        for y, row in enumerate(THERMO):
            for x, bit in enumerate(row):
                if bit == '1':
                    canvas.over(x0 + 2 + x, y, _lin((150, 150, 160), dim * .5), alpha)
        mercury = 6 - level * 5
        for y in range(1, 7):
            if y >= mercury:
                canvas.over(x0 + 3, y, _lin(color, dim), alpha)
        canvas.over(x0 + 3, 6, _lin(color, dim), alpha)


def _ambient(canvas, style, t, info, alpha=1.0, x_from=0):
    """Low, dim style signature on the bottom row (never under the digits)."""
    warm, cool = PALETTES[style]
    for x in range(x_from, 32):
        if style == 'home':
            canvas.add(x, 7, _lin(warm, .14), alpha)
        elif style == 'station':
            if x % 3 == 0:
                canvas.add(x, 7, _lin(cool, .22), alpha)
        elif style == 'nature':
            sway = .5 + .5 * math.sin(x * 1.7 + t * 1.6)
            canvas.add(x, 7, _lin(warm, .1 + .14 * sway), alpha)
        else:
            pulse = math.exp(-((x - (x_from + (t * 9) % (34 - x_from))) ** 2) / 3)
            canvas.add(x, 7, _lin(warm, .1 + .55 * pulse), alpha)
    if style == 'station' and info.get('numeric') is not None and info['key'] != 'conditions':
        # Instrument needle: where the reading sits on its scale.
        span = (info['numeric'] / 100) if info['key'] == 'humidity' else (info['numeric'] + 15) / 50
        x = x_from + fx.clamp01(span) * (31 - x_from)
        canvas.dot(x, 7, _lin(warm), alpha)


def _weather_layer(canvas, category, is_day, t, style):
    """Full-width weather: what the sky is doing right now."""
    warm, cool = PALETTES[style]
    if category == 'clear' and is_day is True:
        for x in range(32):
            for y in range(6):
                canvas.add(x, y, _lin((40, 90, 170), .08 + .03 * (5 - y) / 5))
        canvas.glow(24, 2.3, 3.2, _lin(SUN_YELLOW), 1.4)
        for ray in range(10):
            angle = ray * math.pi / 5 + t * .25
            reach = 4.4 + .6 * math.sin(t * 2 + ray)
            canvas.dot(24 + math.cos(angle) * reach * 1.3, 2.3 + math.sin(angle) * reach * .7, _lin(SUN_YELLOW), .55)
    elif category == 'clear' and is_day is False:
        for star in range(14):
            sx, sy = fx.hash01(star, 61) * 31, fx.hash01(star, 62) * 6
            canvas.add(int(sx), int(sy), _lin((220, 225, 255)), .15 + .25 * (.5 + .5 * math.sin(t * (1 + fx.hash01(star, 63) * 2) + star)))
        draw_icon(canvas, 'moon', t, {}, 1.0, 22)
    elif category == 'clear':
        for x in range(32):
            canvas.add(x, 5, _lin(cool, .25))
    elif category in ('cloudy', 'rain', 'snow', 'storm'):
        dark = category in ('rain', 'storm')
        if category == 'cloudy' and is_day is True:
            canvas.glow(22, 1.5, 2.6, _lin(SUN_YELLOW), 1.0)
        for i, (base, y, speed) in enumerate(((2, 0, .9), (13, 1, .6), (24, 0, .75), (33, 1, .5))):
            x = (base + t * speed) % 40 - 6
            tone = CLOUD_DARK if dark else CLOUD_WHITE
            _cloud(canvas, x, y + (0 if category != 'cloudy' else 1), tone, .85 if i % 2 else 1.0)
        if category in ('rain', 'storm'):
            for drop in range(18):
                speed = 7 + fx.hash01(drop, 1) * 3
                y = 4 + ((t * speed + fx.hash01(drop, 2) * 6) % 4.5)
                x = fx.hash01(drop, 3) * 32 - (y - 4) * .35
                canvas.line(x, y - .8, x - .3, y, _lin(RAIN_BLUE), .55)
        if category == 'snow':
            for flake in range(16):
                y = 4 + ((t * (1 + fx.hash01(flake, 4)) + fx.hash01(flake, 5) * 6) % 4.5)
                x = fx.hash01(flake, 6) * 32 + .8 * math.sin(t * 1.5 + flake)
                canvas.dot(x, y, _lin(SNOW_WHITE), .8)
        if category == 'storm':
            glow = math.sin(t * 1.7) ** 8   # soft swelling glow inside the clouds
            for x in range(32):
                for y in range(4):
                    canvas.add(x, y, _lin((180, 170, 255)), .12 * glow)
            canvas.bitmap(BOLT, 15, 3, _lin(BOLT_YELLOW, .5 + .5 * glow))
    elif category == 'fog':
        for i, y in enumerate((1.5, 3.2, 4.9, 6.4)):
            for x in range(32):
                density = .5 + .5 * math.sin(x * .35 + t * (.5 + i * .15) + i * 2)
                canvas.hline_soft(y, x, x + 1, _lin((185, 195, 210)), .12 + .22 * density)
    else:
        for x in range(4, 28):
            canvas.add(x, 6, _lin(GREY, .3))


def _ground(canvas, style, t):
    warm, cool = PALETTES[style]
    if style == 'home':
        canvas.bitmap(('0110', '1111', '1001', '1111'), 1, 4, _lin(warm, .6))
        canvas.add(2, 6, _lin((255, 200, 90)), .6 + .2 * math.sin(t * 1.3))
    elif style == 'station':
        for y in range(3, 8):
            canvas.over(2, y, _lin(cool, .7))
        for k in range(3):   # spinning anemometer cups
            angle = t * 4 + k * math.tau / 3
            canvas.dot(2 + math.cos(angle) * 1.5, 2.5 + math.sin(angle) * .5, _lin(warm), .9)
    elif style == 'nature':
        for x in (1, 6, 28):
            canvas.bitmap(('010', '111', '111', '010'), x + .25 * math.sin(t + x), 4, _lin(warm, .55))
    else:
        for x in (0, 31):
            for y in range(8):
                canvas.add(x, y, _lin(warm, .25 + .2 * math.sin(t * 2 + y * .8)))


def _scene_canvas(style, t, info):
    canvas = fx.FxCanvas()
    key = info['key']
    warm, cool = PALETTES[style]
    if key in ('outside', 'conditions'):
        _weather_layer(canvas, info.get('category', 'unknown'), info.get('is_day'), t, style)
        _ground(canvas, style, t)
    elif key == 'inside':
        # A warm, lit house; the weather outside stays dim in the background.
        _weather_layer(canvas, info.get('category', 'unknown'), info.get('is_day'), t, style)
        canvas.fade(.3)
        _ground(canvas, style, t)
        roof = ('0000011111100000', '0001111111111000', '0111111111111110')
        canvas.bitmap(roof, 8, 0, _lin(warm, .8))
        for y in range(3, 8):
            for x in range(9, 23):
                edge = x in (9, 22) or y == 7
                canvas.over(x, y, _lin(warm, .45 if edge else .06))
        for wx in (11, 18):
            warmth = .55 + .35 * math.sin(t * 1.1 + wx)
            for dx in range(3):
                for dy in range(2):
                    canvas.over(wx + dx, 4 + dy, _lin((255, 195, 90), warmth))
    else:
        # Humidity: water level rises to the measured value; drops fall in.
        level = (info.get('numeric') or 0) / 100
        surface = 7.6 - level * 6
        for x in range(32):
            wave = surface + .45 * math.sin(x * .45 + t * 2) + .2 * math.sin(x * 1.3 - t * 3)
            for y in range(8):
                depth = fx.smoothstep(wave - .5, wave + .5, y)
                if depth > 0:
                    canvas.add(x, y, _lin(cool, .18 + .3 * depth * (1 - (y - wave) / 10)), depth)
        for i in range(3):
            fall = (t * 2.2 + i * .9) % 2.7
            x = 6 + i * 10 + 2 * math.sin(i * 3.1)
            y = fall * 3 - 1
            if y < surface:
                canvas.dot(x, y, _lin(HUMIDITY['ok']), .9)
            else:
                canvas.glow(x, surface, 1.2, _lin(HUMIDITY['ok']), (2.7 - fall) * .6)
        _ground(canvas, style, t)
    return canvas


def _card_canvas(style, t, info, settings, roll=1.0):
    """Icon + value + optional trend/stale marks. ``roll`` < 1 animates the value in."""
    canvas = fx.FxCanvas()
    trend = info.get('trend') if info.get('trend') in (-1, 1) else None
    room = (28 if trend else 32) - VALUE_X
    text = display_value(info, room)
    color = value_color(info, settings)
    if info['state'] == 'stale':
        color = fx.oklab_mix(color, GREY, .55)
    draw_icon(canvas, icon_key(info), t, info)
    width = fx.text_width(text)
    # Long words (CLOUDS, STORM) may use the gap next to the icon.
    start = max(9, 32 - width) if width > room else VALUE_X + (room - width) // 2
    offsets = [(1 - fx.ease_out_back(fx.clamp01((roll - i * .09) / .55))) * 7 for i in range(len(text))]
    fx.draw_text(canvas, text, start, 1, _lin(color), offsets=offsets, clip=(0, 7))
    if trend and roll >= 1:
        arrow = ('010', '111', '000') if trend == 1 else ('000', '111', '010')
        bob = .5 * math.sin(t * 2.2) * trend
        canvas.bitmap(arrow, 29, 2 - bob, _lin(color, .9), mode='add')
    _ambient(canvas, style, t, info, 1.0, VALUE_X)
    if info['state'] == 'stale':
        # Amber corner: "this value is older than expected".
        canvas.over(31, 0, _lin(STALE, .7 + .3 * math.sin(t * 2)))
        canvas.over(30, 0, _lin(STALE, .45))
    return canvas


def _to_canvas(fxcanvas):
    canvas = Canvas()
    canvas.colors = fxcanvas.to_colors()
    return canvas


def story(style, elapsed, info='outside', intensity='normal'):
    """Full-width scene for one info; deterministic, no IO."""
    if isinstance(info, str): info = dict(key=info, category='unknown', is_day=None)
    t = elapsed * {'calm': .55, 'normal': 1, 'lively': 1.4}[intensity]
    return _to_canvas(_scene_canvas(style, t, info))


def phases(visit):
    read = visit.read_seconds + CARD_EXTRA
    return dict(scene=SCENE_END, card=CARD_IN, read_end=CARD_IN + read, outro_end=CARD_IN + read + OUTRO)


def render(visit, elapsed):
    elapsed = max(0, float(elapsed))
    index = min(len(visit.infos) - 1, max(0, int((elapsed - .8) / visit.segment)))
    info = visit.infos[index]
    style = visit.style
    settings = visit.settings
    speed = {'calm': .55, 'normal': 1, 'lively': 1.4}[settings['weather_intensity']]
    phase = elapsed - .8 - index * visit.segment
    marks = phases(visit)
    t = elapsed * speed
    if elapsed < .8 or phase < marks['scene'] or phase >= marks['outro_end']:
        canvas = _scene_canvas(style, t, info)
    elif phase < marks['card']:
        progress = (phase - marks['scene']) / (marks['card'] - marks['scene'])
        canvas = _scene_canvas(style, t, info)
        canvas.blend(_card_canvas(style, t, info, settings, progress * 1.15), fx.ease_in_out_sine(progress))
    elif phase < marks['read_end']:
        canvas = _card_canvas(style, t, info, settings)
    else:
        progress = (phase - marks['read_end']) / OUTRO
        canvas = _card_canvas(style, t, info, settings)
        canvas.blend(_scene_canvas(style, t, info), fx.ease_in_out_sine(progress))
    colors = canvas.to_colors()
    return ModulePayload(text=info['label'] + ' ' + info['value'],
                         frame=[[int(c is not None) for c in row] for row in colors],
                         color_frame=colors, scene_key=f'weather:{style}:{info["key"]}')


def catalog():
    return dict(styles=[dict(key=key, title=title, description=description)
                        for key, (title, description) in STYLES.items()],
                infos=[dict(key=key, title=title, label=label) for key, (title, label) in INFOS.items()],
                defaults=deepcopy(DEFAULTS))
