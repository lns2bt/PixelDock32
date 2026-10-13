"""Pure, bounded drawing helpers for Time-Stage's 32 × 8 scene library."""

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from app.modules.base import ModulePayload
from app.services.rendering import FONT_3X5


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
        text = now.strftime('%H:%M')
        if blink and now.second % 2:
            text = text.replace(':', ' ')
        self.text(text, x, y, color)

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
