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
ROLL_SECONDS = 0.62
ROLL_STAGGER = 0.07


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
        """HH:MM with a breathing colon and an eased odometer roll per minute.

        Everything is a pure function of wall time, so previews, LEDs and
        tests agree. ``blink`` keeps the classic hard on/off colon.
        """
        text = now.strftime('%H:%M')
        fraction = now.microsecond / 1_000_000
        into_minute = now.second + fraction
        rolling = DIGIT_ROLL.get() and into_minute < ROLL_SECONDS + 4 * ROLL_STAGGER
        previous = (now - timedelta(minutes=1)).strftime('%H:%M') if rolling else text
        for index, char in enumerate(text):
            cx = x + index * 4
            if char == ':':
                if blink:
                    if now.second % 2 == 0:
                        self.bitmap(FONT_3X5[':'], cx, y, color)
                    continue
                # Soft heartbeat: brightest at each full second, never off.
                level = .62 + .38 * (.5 + .5 * math.cos(2 * math.pi * fraction)) ** 2
                self.bitmap(FONT_3X5[':'], cx, y, shade(color, level))
                continue
            old = previous[index]
            if old == char:
                self.bitmap(FONT_3X5.get(char, FONT_3X5[' ']), cx, y, color)
                continue
            # Rightmost digits roll first, like a mechanical counter.
            delay = (len(text) - 1 - index) * ROLL_STAGGER
            t = max(0.0, min(1.0, (into_minute - delay) / ROLL_SECONDS))
            eased = 1 - (1 - t) ** 3
            self._roll_cell(FONT_3X5.get(old, FONT_3X5[' ']), FONT_3X5.get(char, FONT_3X5[' ']),
                            cx, y, color, eased)

    def _roll_cell(self, old_rows, new_rows, x, y, color, eased):
        """Old glyph slides up and out, new glyph rises in (anti-aliased rows)."""
        offset = eased * 6.0
        weights = {}
        for rows, shift in ((old_rows, -offset), (new_rows, 6.0 - offset)):
            for dy, row in enumerate(rows):
                for dx, bit in enumerate(row):
                    if bit != '1':
                        continue
                    position = dy + shift
                    top = math.floor(position)
                    frac = position - top
                    for row_y, weight in ((top, 1 - frac), (top + 1, frac)):
                        if weight > 0.02 and 0 <= row_y < 5:
                            key = (x + dx, y + row_y)
                            weights[key] = min(1.0, weights.get(key, 0.0) + weight)
        for (px, py), weight in weights.items():
            if 0 <= px < 32 and 0 <= py < 8:
                under = self.colors[py][px] or (0, 0, 0)
                self.pixel(px, py, mix(under, color, weight))

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
    count = int(seconds(now) / 60 * 32)
    for x in range(32):
        canvas.pixel(x, y, color if x < count else shade(color, .06))


def event_progress(elapsed, duration):
    return max(0.0, min(1.0, elapsed / duration))
