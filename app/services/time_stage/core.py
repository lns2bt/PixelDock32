"""Pure, bounded drawing helpers for Time-Stage's 32 × 8 scene library."""

from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Callable

from app.modules.base import ModulePayload
from app.services.rendering import FONT_3X5

# Odometer roll of changed digits at each new minute (Time-Stage setting
# ``minute_transition``). A context variable keeps scene renderers pure.
DIGIT_ROLL = ContextVar('digit_roll', default=True)
# Digit-change style for the scene being rendered; set by ``render_scene``.
DIGIT_STYLE = ContextVar('digit_style', default='roll')
DIGIT_STYLES = ('roll', 'flip', 'drop', 'fade', 'decode', 'morph')
ROLL_SECONDS = 0.62
ROLL_STAGGER = 0.07
SECOND_CHANGE = 0.34
_GLYPH_POOL = '0123456789'


@dataclass(frozen=True)
class Scene:
    key: str
    title: str
    style: str
    description: str
    seconds: str
    render: Callable[[datetime, float], 'Canvas']
    duration: float = 8.0
    events: tuple[str, ...] = ()
    digit_style: str = 'roll'
    added: str = ''  # release that introduced the scene (UI "New" badge)


class Canvas:
    def __init__(self):
        self.colors = [[None for _ in range(32)] for _ in range(8)]

    def pixel(self, x, y, color):
        x, y = int(x), int(y)
        if 0 <= x < 32 and 0 <= y < 8:
            rgb = tuple(max(0, min(255, int(c))) for c in color)
            self.colors[y][x] = rgb if any(rgb) else None

    def bitmap(self, rows, x, y, color):
        for dy, row in enumerate(rows):
            for dx, bit in enumerate(row):
                if bit == '1':
                    self.pixel(x + dx, y + dy, color)

    def text(self, text, x=6, y=1, color=(110, 225, 255)):
        for i, char in enumerate(text.upper()):
            self.bitmap(FONT_3X5.get(char, FONT_3X5[' ']), x + i * 4, y, color)

    def clock(self, now, color=(110, 225, 255), x=6, y=1, blink=False):
        """HH:MM with a breathing colon and an animated minute change.

        Everything is a pure function of wall time, so previews, LEDs and
        tests agree. ``blink`` keeps the classic hard on/off colon.
        """
        self.ticker(now, '%H:%M', x, y, color, unit='minute', blink=blink)

    def ticker(self, now, fmt, x, y, color, unit='minute', blink=False, positions=None, colors=None):
        """Draw ``now.strftime(fmt)`` and animate characters that just changed.

        ``unit`` is the smallest field in ``fmt`` (minute or second); the
        change animation uses the active ``DIGIT_STYLE``. ``positions`` may
        override the x position of each character, ``colors`` its colour.
        """
        text = now.strftime(fmt)
        fraction = now.microsecond / 1_000_000
        if unit == 'second':
            since, span, stagger = fraction, SECOND_CHANGE, 0.03
            previous_time = now - timedelta(seconds=1)
        else:
            since, span, stagger = now.second + fraction, ROLL_SECONDS, ROLL_STAGGER
            previous_time = now - timedelta(minutes=1)
        animating = DIGIT_ROLL.get() and since < span + len(text) * stagger
        previous = previous_time.strftime(fmt) if animating else text
        style = DIGIT_STYLE.get()
        for index, char in enumerate(text):
            cx = positions[index] if positions else x + index * 4
            tint = colors[index] if colors and index < len(colors) else color
            if char == ':':
                if blink:
                    if now.second % 2 == 0:
                        self.bitmap(FONT_3X5[':'], cx, y, tint)
                    continue
                # Soft heartbeat: brightest at each full second, never off.
                level = .62 + .38 * (.5 + .5 * math.cos(2 * math.pi * fraction)) ** 2
                self.bitmap(FONT_3X5[':'], cx, y, shade(tint, level))
                continue
            old = previous[index] if index < len(previous) else char
            if old == char:
                self.bitmap(FONT_3X5.get(char, FONT_3X5[' ']), cx, y, tint)
                continue
            # Rightmost characters change first, like a mechanical counter.
            delay = (len(text) - 1 - index) * stagger
            t = max(0.0, min(1.0, (since - delay) / span))
            self.change_cell(FONT_3X5.get(old, FONT_3X5[' ']), FONT_3X5.get(char, FONT_3X5[' ']),
                             cx, y, tint, t, style, seed=index)

    def change_cell(self, old_rows, new_rows, x, y, color, t, style='roll', seed=0):
        """Blend one 3 × 5 character from ``old_rows`` to ``new_rows`` (t = 0…1)."""
        weights = _CHANGE.get(style, _change_roll)(old_rows, new_rows, t, seed)
        for (dx, dy), weight in weights.items():
            px, py = x + dx, y + dy
            if weight > 0.02 and 0 <= px < 32 and 0 <= py < 8:
                under = self.colors[py][px] or (0, 0, 0)
                self.pixel(px, py, mix(under, color, min(1.0, weight)))

    # -- anti-aliased helpers (sub-pixel motion on the integer canvas) ---- #
    def blend(self, x, y, color, alpha):
        """Mix ``color`` over the existing pixel with coverage ``alpha``."""
        x, y = int(x), int(y)
        if alpha <= 0.01 or not (0 <= x < 32 and 0 <= y < 8):
            return
        under = self.colors[y][x] or (0, 0, 0)
        if alpha >= 1:
            self.pixel(x, y, color)
        else:
            self.pixel(x, y, tuple(max(u, int(u * (1 - alpha) + c * alpha)) for u, c in zip(under, color)))

    def dot(self, x, y, color, alpha=1.0):
        """Bilinear sub-pixel point: glides smoothly between pixel centres."""
        x0, y0 = math.floor(x), math.floor(y)
        fx, fy = x - x0, y - y0
        for px, py, weight in ((x0, y0, (1 - fx) * (1 - fy)), (x0 + 1, y0, fx * (1 - fy)),
                               (x0, y0 + 1, (1 - fx) * fy), (x0 + 1, y0 + 1, fx * fy)):
            self.blend(px, py, color, alpha * weight ** .8)

    def sprite(self, rows, x, y, color, alpha=1.0):
        """1-bit sprite at a fractional position (anti-aliased edges)."""
        for dy, row in enumerate(rows):
            for dx, bit in enumerate(row):
                if bit == '1':
                    self.dot(x + dx, y + dy, color, alpha)

    def glow(self, x, y, radius, color, alpha=1.0, stretch=1.0):
        reach = radius + 1
        for py in range(max(0, int(y - reach)), min(8, int(y + reach) + 2)):
            for px in range(max(0, int(x - reach * stretch)), min(32, int(x + reach * stretch) + 2)):
                d2 = (((px - x) / stretch) ** 2 + (py - y) ** 2) / (radius * radius)
                if d2 < 1:
                    self.blend(px, py, color, alpha * (1 - d2) ** 2)

    def track(self, points, position, color, tail=0, tail_level=.6):
        """A head travelling along ``points`` with a fading tail, sub-pixel smooth."""
        count = len(points)
        if not count:
            return
        for step in range(tail, -1, -1):
            where = (position - step) % count
            index = int(where)
            frac = where - index
            level = 1.0 if step == 0 else tail_level * (1 - step / (tail + 1))
            a, b = points[index], points[(index + 1) % count]
            if abs(a[0] - b[0]) + abs(a[1] - b[1]) > 2:
                self.blend(*a, color, level)
                continue
            self.blend(*a, color, level * (1 - frac))
            self.blend(*b, color, level * frac)

    def payload(self, now, key):
        frame = [[int(color is not None) for color in row] for row in self.colors]
        return ModulePayload(text=now.strftime('%H:%M'), frame=frame, color_frame=self.colors, scene_key=key)


def seconds(now: datetime):
    """Wall-clock position in the minute; independent of a playlist visit."""
    return now.second + now.microsecond / 1_000_000


def shade(color, amount):
    return tuple(max(0, min(255, int(c * amount))) for c in color)


def mix(a, b, amount):
    amount = max(0, min(1, amount))
    return tuple(int(x * (1 - amount) + y * amount) for x, y in zip(a, b))


def perimeter():
    return ([(x, 0) for x in range(32)] + [(31, y) for y in range(1, 7)]
            + [(x, 7) for x in range(31, -1, -1)] + [(0, y) for y in range(6, 0, -1)])


def progress(canvas, now, color, y=7):
    """Minute bar whose leading pixel fills continuously (no 2-second jumps)."""
    filled = seconds(now) / 60 * 32
    for x in range(32):
        amount = max(0.0, min(1.0, filled - x))
        canvas.pixel(x, y, mix(shade(color, .06), color, amount))


def event_progress(elapsed, duration):
    return max(0.0, min(1.0, elapsed / duration))


# --------------------------------------------------------------------------- #
# Digit change styles: each returns {(dx, dy): coverage} for a 3 × 5 cell.
# --------------------------------------------------------------------------- #

def _ease_out(t):
    return 1 - (1 - t) ** 3


def _bits(rows):
    return [(dx, dy) for dy, row in enumerate(rows) for dx, bit in enumerate(row) if bit == '1']


def _splat_rows(weights, rows, shift, level=1.0, clip=(0, 5)):
    for dx, dy in _bits(rows):
        position = dy + shift
        top = math.floor(position)
        frac = position - top
        for row_y, weight in ((top, 1 - frac), (top + 1, frac)):
            if weight > 0.02 and clip[0] <= row_y < clip[1]:
                key = (dx, row_y)
                weights[key] = min(1.0, weights.get(key, 0.0) + weight * level)
    return weights


def _change_roll(old, new, t, seed):
    """Odometer: old glyph slides up and out, new glyph rises in."""
    offset = _ease_out(t) * 6.0
    weights = {}
    _splat_rows(weights, old, -offset)
    _splat_rows(weights, new, 6.0 - offset)
    return weights


def _change_drop(old, new, t, seed):
    """Old glyph falls away, new glyph drops in from above with a small bounce."""
    weights = {}
    if t < .45:
        fall = (t / .45) ** 2 * 6
        _splat_rows(weights, old, fall)
    u = max(0.0, (t - .15) / .85)
    if u > 0:
        # Damped bounce: overshoot by a pixel, settle at zero.
        bounce = 1 - (1 - u) ** 2.2 * math.cos(u * math.pi * 1.6)
        _splat_rows(weights, new, -6 + 6 * bounce)
    return weights


def _change_fade(old, new, t, seed):
    eased = t * t * (3 - 2 * t)
    weights = {}
    for dx, dy in _bits(old):
        weights[(dx, dy)] = 1 - eased
    for dx, dy in _bits(new):
        weights[(dx, dy)] = max(weights.get((dx, dy), 0.0), eased)
    return weights


def _change_flip(old, new, t, seed):
    """Split-flap: the upper half folds down over the hinge (row 2)."""
    weights = {}
    hinge = 2
    if t < .5:
        p = _ease_out(t / .5) if t > 0 else 0.0
        for dx, dy in _bits(new):
            if dy < hinge:
                weights[(dx, dy)] = .45          # revealed top of the next card
        for dx, dy in _bits(old):
            if dy >= hinge:
                weights[(dx, dy)] = 1.0          # bottom of the current card
        # Falling flap: old top half squashed towards the hinge.
        height = (1 - p) * hinge
        for dx, dy in _bits(old):
            if dy < hinge and height > .05:
                y = hinge - (hinge - dy) * height / hinge
                top = math.floor(y)
                frac = y - top
                for row_y, weight in ((top, 1 - frac), (top + 1, frac)):
                    if weight > .05 and 0 <= row_y <= hinge:
                        weights[(dx, row_y)] = max(weights.get((dx, row_y), 0.0), weight * (1 - .4 * p))
    else:
        p = _ease_out((t - .5) / .5)
        for dx, dy in _bits(new):
            if dy <= hinge:
                weights[(dx, dy)] = 1.0
        for dx, dy in _bits(old):
            if dy > hinge:
                weights[(dx, dy)] = .5 * (1 - p)
        # The new card's bottom half unfolds below the hinge.
        span = 4 - hinge
        for dx, dy in _bits(new):
            if dy > hinge:
                y = hinge + (dy - hinge) * p
                top = math.floor(y)
                frac = y - top
                for row_y, weight in ((top, 1 - frac), (top + 1, frac)):
                    if weight > .05 and hinge <= row_y <= 4:
                        weights[(dx, row_y)] = max(weights.get((dx, row_y), 0.0), weight * (.6 + .4 * p))
        del span
    return weights


def _change_decode(old, new, t, seed):
    """Matrix decode: a few scrambled glyphs, then the real one locks in."""
    from app.services.fx import hash01
    if t >= .72:
        settle = (t - .72) / .28
        return {(dx, dy): .7 + .3 * settle for dx, dy in _bits(new)}
    step = int(t * 14)
    glyph = FONT_3X5[_GLYPH_POOL[int(hash01(seed, step, 404) * len(_GLYPH_POOL))]]
    level = .45 + .25 * (step % 2)
    return {(dx, dy): level for dx, dy in _bits(glyph)}


def _change_morph(old, new, t, seed):
    """Each lit pixel travels to a pixel of the new glyph."""
    a, b = _bits(old), _bits(new)
    if not a or not b:
        return _change_fade(old, new, t, seed)
    eased = t * t * (3 - 2 * t)
    count = max(len(a), len(b))
    weights = {}
    for index in range(count):
        ax, ay = a[index * len(a) // count]
        bx, by = b[index * len(b) // count]
        x, y = ax + (bx - ax) * eased, ay + (by - ay) * eased
        x0, y0 = math.floor(x), math.floor(y)
        fx, fy = x - x0, y - y0
        for px, py, w in ((x0, y0, (1 - fx) * (1 - fy)), (x0 + 1, y0, fx * (1 - fy)),
                          (x0, y0 + 1, (1 - fx) * fy), (x0 + 1, y0 + 1, fx * fy)):
            if w > .03 and 0 <= px < 3 and 0 <= py < 5:
                weights[(px, py)] = max(weights.get((px, py), 0.0), w ** .7)
    return weights


_CHANGE = {
    'roll': _change_roll, 'flip': _change_flip, 'drop': _change_drop,
    'fade': _change_fade, 'decode': _change_decode, 'morph': _change_morph,
}
