"""Pure, bounded 32×8 weather stories; one coherent style per frozen visit."""
from copy import deepcopy
from dataclasses import dataclass
import math
import random
import time

from app.modules.base import ModulePayload
from app.services.bitcoin_stage import FairRotation, box, line, text
from app.services.time_stage.core import Canvas, shade


STYLES = {
    'home': ('Pixel-Zuhause', 'Vom Wetter vor dem Haus ins warme Zimmer'),
    'station': ('Wetterstation', 'Ruhige Instrumente und Messskalen'),
    'nature': ('Naturwelt', 'Himmel, Wald und Wasser ohne Gesundheitsversprechen'),
    'neon': ('Neon-Labor', 'Leuchtende Messkammern und klare Daten'),
}
INFOS = {
    'outside': ('Außentemperatur', 'AUSSEN'),
    'inside': ('Innentemperatur', 'INNEN'),
    'humidity': ('Luftfeuchtigkeit innen', 'FEUCHTE'),
    'conditions': ('Wetter draußen', 'WETTER'),
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
CLOUD = ('0011100', '0111110', '1111111')
DROP = ('00100', '00100', '01110', '11111', '01110')
CRESCENT = ('0110', '1100', '1100', '1100', '0110')
THERMOMETER = ('010', '010', '010', '111', '111')


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
        value = {'clear': 'SONNE' if is_day is True else 'MOND' if is_day is False else 'KLAR',
                 'cloudy': 'WOLKEN', 'fog': 'NEBEL', 'rain': 'REGEN',
                 'snow': 'SCHNEE', 'storm': 'GEWITTER'}[category]
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


def sky(canvas, category, is_day, t, color):
    """Known weather only, with a sparse, non-flashing storm silhouette."""
    if category == 'clear':
        if is_day is True:
            rise = max(0, 2-int(min(2, t)))
            box(canvas, 14, 2+rise, 3, 3, color, True)
            for x, y in ((15, 0), (15, 6), (12, 3), (19, 3), (12, 0), (19, 6)):
                canvas.pixel(x, y, shade(color, .5+.15*math.sin(t*2+x)))
        elif is_day is False:
            canvas.bitmap(CRESCENT, 14, 1, color)
            for x, y in ((4, 1), (9, 4), (24, 2), (28, 5)): canvas.pixel(x, y, shade(color, .45+.15*math.sin(t+x)))
        else:
            line(canvas, 10, 5, 22, 5, shade(color, .4))
    elif category in ('cloudy', 'rain', 'snow', 'storm'):
        drift=int(t*.7)%5-2
        canvas.bitmap(CLOUD, 12+drift, 0, color)
        if category == 'cloudy': canvas.bitmap(CLOUD, 21-drift, 3, shade(color, .55))
        if category in ('rain', 'snow', 'storm'):
            for i in range(5):
                x = 8 + i * 4
                y = 3 + int(t * (2 if category == 'snow' else 3) + i) % 4
                canvas.pixel(x, y, shade(color, .7))
                if category == 'snow': canvas.pixel(x + 1, y, shade(color, .35))
                elif y == 6:
                    canvas.pixel(x - 1, 7, shade(color, .45)); canvas.pixel(x + 1, 7, shade(color, .45))
        if category == 'storm':
            # No full-frame flash or on/off strobe, even at lively intensity.
            canvas.bitmap(('001', '010', '110', '010'), 15, 3, shade(color, .65))
            canvas.pixel(23, 5 + int(t) % 2, shade(color, .3))
    elif category == 'fog':
        for y in (2, 4, 6):
            for x in range(5, 28):
                if (x + y + int(t)) % 9 < 7: canvas.pixel(x, y, shade(color, .35))
    else:
        # Neutral horizon: missing weather never looks like a sunny forecast.
        line(canvas, 7, 6, 25, 6, shade(color, .25))


def story(style, elapsed, info='outside', intensity='normal'):
    """Fixed-size assets and deterministic motion; no IO, images, or random pixels."""
    if isinstance(info, str): info = dict(key=info, category='unknown', is_day=None)
    key = info['key']
    canvas = Canvas()
    warm, cool = PALETTES[style]
    t = elapsed * {'calm': .55, 'normal': 1, 'lively': 1.4}[intensity]
    # Motif motion only. The reading phase never calls this scene renderer.
    build=max(0,min(1,(elapsed-.8)/1.4))
    numeric=info.get('numeric')
    level=None if numeric is None else max(0,min(1,numeric/100 if key=='humidity' else (numeric+10)/50))
    if style == 'home':
        if key in ('outside', 'conditions'):
            line(canvas, 0, 7, 31, 7, shade(warm, .3))
            line(canvas, 0, 4, 3, 1, warm); line(canvas, 3, 1, 6, 4, warm)
            box(canvas, 1, 4, 5, 4, shade(warm, .65))
            sky(canvas, info.get('category', 'unknown'), info.get('is_day'), t, cool)
            if key == 'outside': canvas.bitmap(THERMOMETER, 28, 2, warm)
        elif key == 'inside':
            line(canvas, 0, 7, 31, 7, shade(warm, .3))
            box(canvas, 10, 3, 10, 4, warm); line(canvas, 9, 6, 21, 6, warm)
            canvas.bitmap(('01110', '11111'), 24, 1, warm)
            line(canvas, 26, 3, 26, 7, shade(warm, .6))
            box(canvas, 2, 0, 5, 5, shade(cool, .5))
            for x in range(23,30):
                canvas.pixel(x,5,shade(warm,(.15+.25*build)*(1-abs(x-26)/5)))
            canvas.pixel(26,7-int(t*2)%4,shade(warm,.35))
        else:
            box(canvas, 1, 0, 8, 7, shade(warm, .4))
            canvas.bitmap(DROP, 16, max(0,2-int(t)%3), cool)
            for x in range(13,24):canvas.pixel(x,6+(x+int(t*3))%2,shade(cool,.4))
    elif style == 'station':
        box(canvas, 0, 0, 32, 8, shade(cool, .35))
        for x in range(3, 30, 4): canvas.pixel(x, 7, warm)
        if key in ('outside', 'conditions'):
            sky(canvas, info.get('category', 'unknown'), info.get('is_day'), t, warm)
            if key == 'outside': canvas.bitmap(THERMOMETER, 2, 1, cool)
        elif key == 'inside':
            canvas.bitmap(THERMOMETER, 14, 1, warm)
            for y in (1, 3, 5): line(canvas, 21, y, 25, y, cool)
        else:
            canvas.bitmap(DROP, 14, 1, warm)
            line(canvas, 4, 5, 8, 2, cool); line(canvas, 24, 2, 28, 5, cool)
        if level is not None:
            for x in range(3,3+int(25*level*build)):canvas.pixel(x,6,shade(warm,.75))
    elif style == 'nature':
        for x in (1, 5, 27):
            canvas.bitmap(('010', '111', '010', '010'), x, 4, shade(warm, .55))
            canvas.pixel(x+int(t)%2,3,shade(warm,.35))
        if key in ('outside', 'conditions'):
            sky(canvas, info.get('category', 'unknown'), info.get('is_day'), t, cool)
            if key == 'outside': canvas.bitmap(THERMOMETER, 21, 2, warm)
        elif key == 'inside':
            line(canvas, 11, 3, 16, 0, warm); line(canvas, 16, 0, 21, 3, warm)
            box(canvas, 12, 3, 9, 5, warm); box(canvas, 15, 4, 3, 4, cool)
            canvas.pixel(16,5,shade(cool,.45+.2*build))
        else:
            canvas.bitmap(DROP, 14, 0, cool)
            for x in range(8, 25): canvas.pixel(x, 6 + (x + int(t)) % 2, shade(cool, .5))
    else:  # neon laboratory
        for x in (0, 31): line(canvas, x, 0, x, 7, warm)
        for x in range(3, 30, 5): canvas.pixel(x, 7, shade(cool, .5))
        if key in ('outside', 'conditions'):
            sky(canvas, info.get('category', 'unknown'), info.get('is_day'), t, cool)
            if key == 'outside': box(canvas, 3, 1, 4, 5, warm)
        elif key == 'inside':
            box(canvas, 8, 0, 16, 7, shade(warm, .5))
            canvas.bitmap(THERMOMETER, 14, 1, cool)
            line(canvas, 10, 5, 12, 3, warm); line(canvas, 20, 3, 22, 5, warm)
        else:
            box(canvas, 10, 0, 12, 7, shade(warm, .5))
            canvas.bitmap(DROP, 14, 1, cool)
        if level is not None:
            for y in range(6,6-int(5*level*build),-1):
                line(canvas,11,y,20,y,shade(cool,.3))
        canvas.pixel(3+int(t*4)%25,7,cool)
    # Only an explicitly measured trend may add a direction cue.
    trend = info.get('trend')
    if trend in (-1, 1):
        canvas.bitmap(('010', '111') if trend == 1 else ('111', '010'), 28, 1, warm)
    return canvas


def render(visit, elapsed):
    elapsed = max(0, float(elapsed))
    index = min(len(visit.infos) - 1, max(0, int((elapsed - .8) / visit.segment)))
    info = visit.infos[index]
    prefix = {'outside':'A ', 'inside':'I ', 'humidity':'H '}.get(info['key'], '')
    display_value = prefix + info['value']
    phase = elapsed - .8 - index * visit.segment
    style = visit.style
    warm, cool = PALETTES[style]
    color = (145, 145, 150) if info['state'] == 'missing' else warm
    if info['key'] == 'inside' and info.get('numeric') is not None:
        if info['numeric'] < visit.settings['weather_comfort_min']: color = cool
        elif info['numeric'] > visit.settings['weather_comfort_max']: color = (255, 130, 95)
    canvas = Canvas()
    motif = lambda: story(style, elapsed if elapsed < .8 else phase, info,
                          visit.settings['weather_intensity'])
    if elapsed < .8:
        canvas = motif()
    elif phase < .9:
        text(canvas, info['label'], phase, cool)
    elif phase < 2.2:
        canvas = motif()
    elif phase < 2.9:
        canvas = motif()
        target = Canvas(); text(target, display_value, 0, color)
        progress = (phase - 2.2) / .7
        for y in range(8):
            for x in range(32):
                reveal = (y / 8 if style == 'nature' else x / 32 if style in ('station', 'neon')
                          else abs(x - 16) / 16) < progress
                if reveal: canvas.colors[y][x] = target.colors[y][x]
    elif phase < 2.9 + visit.read_seconds:
        text(canvas, display_value, phase - 2.9, color)
        if info['state'] == 'stale':
            canvas.pixel(0, 0, (255, 65, 20)); canvas.pixel(1, 0, (255, 65, 20))
        elif info['state'] == 'missing': canvas.pixel(0, 0, (150, 150, 150))
        for x in range(32):
            if x % {'home': 5, 'station': 3, 'nature': 6, 'neon': 4}[style] == 0:
                canvas.pixel(x, 7, shade(cool, .2))
    else:
        canvas = motif()  # Art-only transition and outro; no label encore.
    return ModulePayload(text=info['label'] + ' ' + info['value'],
                         frame=[[int(c is not None) for c in row] for row in canvas.colors],
                         color_frame=canvas.colors, scene_key=f'weather:{style}:{info["key"]}')


def catalog():
    return dict(styles=[dict(key=key, title=title, description=description)
                        for key, (title, description) in STYLES.items()],
                infos=[dict(key=key, title=title, label=label) for key, (title, label) in INFOS.items()],
                defaults=deepcopy(DEFAULTS))
