"""Small purposeful symbols and readable typography for a 32x8 panel."""

import math

from app.modules.base import ModulePayload
from app.services.rendering import FONT_3X5

ICONS = {
    "sun": ["00100", "10101", "01110", "11111", "01110", "10101", "00100"],
    "house": ["00100", "01110", "11111", "10001", "10101", "10101", "11111"],
    "drop": ["00100", "00100", "01110", "01110", "11111", "11111", "01110"],
    "coin": ["01110", "10101", "11110", "10101", "11110", "10101", "01110"],
    "hero": ["01110", "11111", "01110", "00100", "01110", "10101", "01010"],
}


def canvas():
    return [[0] * 32 for _ in range(8)], [[None] * 32 for _ in range(8)]


def paint(frame, colors, bitmap, x, y, color):
    for dy, row in enumerate(bitmap):
        for dx, bit in enumerate(row):
            tx, ty = x + dx, y + dy
            if bit == "1" and 0 <= tx < 32 and 0 <= ty < 8:
                frame[ty][tx], colors[ty][tx] = 1, color


def label(frame, colors, text, x, y, color):
    for char in text:
        paint(frame, colors, FONT_3X5.get(char, FONT_3X5[" "]), x, y, color)
        x += 4


def icon_value(icon, text, color, elapsed=0):
    frame, colors = canvas()
    glow = 0.75 + 0.25 * math.sin(elapsed * 3)
    paint(frame, colors, ICONS[icon], 0, 0, tuple(int(v * glow) for v in color))
    label(frame, colors, text[:6], 7, 1, color)
    return ModulePayload(text=text, frame=frame, color_frame=colors, scene_key=icon)


def clock_visual(now, settings):
    from app.services.colors import parse_hex_color
    elapsed = settings.get("_elapsed", 0)
    variants = settings.get("variants", ["classic", "arcade", "progress"])
    valid = [v for v in variants if v in {"classic", "arcade", "progress", "binary"}]
    variants = valid or ["classic"]
    index = (settings.get("_visit", 0) + int(elapsed / max(2, settings.get("variant_seconds", 4)))) % len(variants)
    variant = variants[index]
    color = parse_hex_color(settings.get("color"), (110, 225, 255))
    frame, colors = canvas()
    text = now.strftime("%H:%M")
    if variant == "classic":
        show_seconds = settings.get("show_seconds", True)
        text = now.strftime("%H:%M:%S" if show_seconds else "%H:%M")
        label(frame, colors, text, 0 if show_seconds else 6, 1, color)
    elif variant == "arcade":
        hero = list(ICONS["hero"])
        if int(elapsed * 4) % 2:
            hero[-1] = "10001"
        paint(frame, colors, hero, 0, 0, (255, 195, 65))
        label(frame, colors, text, 8, 1, color)
        x = 7 + int(now.second / 60 * 24)
        frame[7][x], colors[7][x] = 1, (255, 195, 65)
    else:
        label(frame, colors, text, 6, 0, color)
        if variant == "progress":
            progress = int(now.second / 60 * 32)
            for x in range(32):
                frame[7][x], colors[7][x] = 1, (165, 110, 245) if x <= progress else (12, 18, 35)
        else:
            for digit, value in enumerate(now.strftime("%H%M")):
                for bit in range(4):
                    x = 4 + digit * 7 + bit
                    frame[7][x], colors[7][x] = 1, (255, 195, 65) if int(value) & (1 << (3 - bit)) else (12, 18, 35)
    return ModulePayload(text=text, frame=frame, color_frame=colors, scene_key=variant)
