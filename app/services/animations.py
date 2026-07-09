import colorsys
import math
from collections.abc import Callable

Frame = list[list[int]]
Color = tuple[int, int, int]
ColorFrame = list[list[Color | None]]
AnimationFrame = tuple[Frame, ColorFrame]


def hsv_to_rgb(h: float, s: float, v: float) -> Color:
    """Convert HSV values to an RGB tuple with 8-bit channels.

    ``h`` wraps around the unit color wheel, while ``s`` and ``v`` are clamped
    to the 0..1 range so callers can feed in continuous animation math without
    having to guard the values first.
    """
    hue = float(h) % 1.0
    saturation = max(0.0, min(1.0, float(s)))
    value = max(0.0, min(1.0, float(v)))
    r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
    return (round(r * 255), round(g * 255), round(b * 255))


def blank_color_frame(width: int = 32, height: int = 8) -> ColorFrame:
    return [[None for _ in range(width)] for _ in range(height)]


def frame_from_color_frame(color_frame: ColorFrame) -> Frame:
    return [[1 if pixel is not None else 0 for pixel in row] for row in color_frame]


def rainbow_wave(tick: float, width: int = 32, height: int = 8) -> AnimationFrame:
    color_frame = blank_color_frame(width, height)
    phase = float(tick) * 0.18
    for y in range(height):
        for x in range(width):
            hue = (x / max(width, 1)) + (y / max(height, 1)) * 0.12 + phase
            shimmer = 0.72 + 0.28 * math.sin((x * 0.45) + (y * 0.9) + (float(tick) * 2.0))
            color_frame[y][x] = hsv_to_rgb(hue, 1.0, shimmer)
    return frame_from_color_frame(color_frame), color_frame


def color_comet(tick: float, width: int = 32, height: int = 8) -> AnimationFrame:
    color_frame = blank_color_frame(width, height)
    total = max(width * height, 1)
    head = (float(tick) * 24.0) % total
    tail_length = 42.0
    for y in range(height):
        for x in range(width):
            idx = y * width + x
            distance = (head - idx) % total
            if distance > tail_length:
                continue
            brightness = (1.0 - (distance / tail_length)) ** 1.8
            hue = (float(tick) * 0.12 + idx / total) % 1.0
            color_frame[y][x] = hsv_to_rgb(hue, 0.9, max(0.08, brightness))
    return frame_from_color_frame(color_frame), color_frame


ANIMATION_FACTORIES: dict[str, Callable[[float], AnimationFrame]] = {
    "rainbow_wave": lambda tick: rainbow_wave(tick),
    "color_comet": lambda tick: color_comet(tick),
}
