"""Ambient animations for the 32 × 8 matrix.

Every preset draws into a linear-light :class:`FxCanvas` with sub-pixel,
anti-aliased motion and OKLab gradients, and is a deterministic function of
time (plus a small, self-healing cache for Game of Life). That keeps previews,
tests and the physical LEDs identical.
"""

from __future__ import annotations

import math
import time

from app.modules.base import ModuleBase, ModulePayload
from app.services.fx import (
    FxCanvas, Gradient, clamp01, ease_in_out_sine, fbm2, hash01, noise2, smoothstep, to_linear,
)

WIDTH = 32
HEIGHT = 8

# key → (title, description, signature palette used by palette="auto")
PRESET_INFO: dict[str, tuple[str, str, str]] = {
    "psychedelic_plasma": ("Psychedelic Plasma", "Flowing interference colours", "neon"),
    "retro_rainbow_tunnel": ("Rainbow Tunnel", "Soft concentric rings racing outwards", "rainbow"),
    "bit_invaders": ("Bit Invaders", "Gliding pixel aliens over a starfield", "neon"),
    "neon_equalizer": ("Neon Equalizer", "Smooth bars with falling peak markers", "neon"),
    "matrix_rain": ("Matrix Rain", "Glowing code drops with long afterglow", "matrix"),
    "lava_lamp": ("Lava Lamp", "Soft merging blobs", "sunset"),
    "pixel_snake": ("Pixel Snake", "A gliding snake with a fading tail", "rainbow"),
    "aurora": ("Aurora", "Northern lights curtains over a starry sky", "aurora"),
    "ripple": ("Water Ripple", "Raindrops sending rings across a pond", "ocean"),
    "fireflies": ("Fireflies", "Drifting, softly pulsing lights", "forest"),
    "sine_ribbons": ("Sine Ribbons", "Overlapping neon light ribbons", "neon"),
    "synthwave": ("Synthwave", "Retro sun over a moving grid", "sunset"),
    "embers": ("Embers", "Glowing coals with rising sparks", "fire"),
    "game_of_life": ("Game of Life", "Cells that are born and fade gently", "ocean"),
    "starfield": ("Starfield", "Parallax stars with warp bursts", "ice"),
}
PRESETS = set(PRESET_INFO)

PALETTES: dict[str, list[tuple[int, int, int]]] = {
    "neon": [(255, 0, 180), (0, 240, 255), (120, 255, 0), (255, 220, 0), (140, 80, 255)],
    "rainbow": [(255, 0, 0), (255, 130, 0), (255, 255, 0), (0, 220, 70), (0, 170, 255), (100, 70, 255), (220, 0, 255)],
    "fire": [(80, 0, 0), (220, 24, 0), (255, 120, 0), (255, 220, 80), (255, 255, 190)],
    "ocean": [(0, 25, 80), (0, 100, 180), (0, 210, 220), (120, 255, 210), (220, 255, 255)],
    "matrix": [(0, 40, 0), (0, 150, 35), (70, 255, 100), (210, 255, 210)],
    "aurora": [(10, 30, 90), (20, 210, 120), (60, 255, 170), (120, 90, 255), (220, 80, 220)],
    "sunset": [(60, 10, 110), (200, 30, 160), (255, 70, 120), (255, 150, 60), (255, 230, 120)],
    "ice": [(20, 40, 120), (70, 140, 255), (160, 220, 255), (240, 250, 255)],
    "forest": [(10, 50, 20), (90, 190, 40), (210, 255, 80), (255, 190, 60)],
}
PALETTE_CHOICES = ["auto", *PALETTES]

ALIEN = [
    "00100100",
    "01111110",
    "11011011",
    "11111111",
    "01111110",
    "01011010",
    "10000001",
    "01000010",
]
ALIEN_B = [
    "00100100",
    "01111110",
    "11011011",
    "11111111",
    "01111110",
    "00100100",
    "01011010",
    "10100101",
]


def _luma(color) -> float:
    return 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]


class Palette:
    def __init__(self, colors: list[tuple[int, int, int]]):
        self.colors = colors
        self.linear = [to_linear(color) for color in colors]
        self.cycle = Gradient(colors, cyclic=True)
        ordered = sorted(colors, key=_luma)
        self.ramp = Gradient([(0, 0, 0), *ordered])
        self.bright = max(colors, key=_luma)


_PALETTE_CACHE = {name: Palette(colors) for name, colors in PALETTES.items()}


def _palette(name: object, preset: str) -> Palette:
    key = str(name).strip().lower()
    if key == "auto" or key not in PALETTES:
        key = PRESET_INFO.get(preset, ("", "", "neon"))[2] if key == "auto" else "neon"
    return _PALETTE_CACHE[key]


def _blank() -> tuple[list[list[int]], list[list[tuple[int, int, int] | None]]]:
    return [[0 for _ in range(WIDTH)] for _ in range(HEIGHT)], [[None for _ in range(WIDTH)] for _ in range(HEIGHT)]


class AnimationsModule(ModuleBase):
    key = "animations"

    def __init__(self):
        self._life_cache: dict = {}

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        preset = str(settings.get("preset", "psychedelic_plasma")).strip().lower()
        if preset not in PRESETS:
            preset = "psychedelic_plasma"
        try:
            speed = max(0.1, min(5.0, float(settings.get("speed", 1.0))))
        except (TypeError, ValueError):
            speed = 1.0
        try:
            intensity = max(0.1, min(1.0, float(settings.get("intensity", 0.8))))
        except (TypeError, ValueError):
            intensity = 0.8
        mirror_mode = str(settings.get("mirror_mode", "none")).strip().lower()
        if mirror_mode not in {"none", "horizontal", "vertical", "quad"}:
            mirror_mode = "none"
        palette = _palette(settings.get("palette", "auto"), preset)
        t = float(settings.get("_elapsed", time.monotonic())) * speed

        canvas = FxCanvas()
        getattr(self, f"_{preset}")(canvas, t, palette)
        # Intensity is perceptual (like the brightness slider), applied in linear light.
        frame, color_frame = canvas.to_frames(intensity ** 2.2)
        frame, color_frame = self._mirror(frame, color_frame, mirror_mode)
        return ModulePayload(text="", frame=frame, color_frame=color_frame)

    def _mirror(self, frame, color_frame, mode: str):
        if mode == "none":
            return frame, color_frame
        out, out_colors = _blank()
        for y in range(HEIGHT):
            for x in range(WIDTH):
                if not frame[y][x]:
                    continue
                targets = {(x, y)}
                if mode in {"horizontal", "quad"}:
                    targets.add((WIDTH - 1 - x, y))
                if mode in {"vertical", "quad"}:
                    targets.add((x, HEIGHT - 1 - y))
                if mode == "quad":
                    targets.add((WIDTH - 1 - x, HEIGHT - 1 - y))
                for tx, ty in targets:
                    out[ty][tx] = 1
                    out_colors[ty][tx] = color_frame[y][x]
        return out, out_colors

    # ------------------------------------------------------------------ #
    # Reworked classics
    # ------------------------------------------------------------------ #
    def _psychedelic_plasma(self, c: FxCanvas, t, pal: Palette):
        sin, cos = math.sin, math.cos
        for y in range(HEIGHT):
            for x in range(WIDTH):
                v = sin(x * 0.34 + t) + cos(y * 0.95 - t * 1.2) + sin((x + y) * 0.22 + t * 0.7)
                v += sin(math.hypot(x - 16 - 8 * sin(t * 0.3), (y - 4) * 3) * 0.35 - t)
                depth = 0.55 + 0.45 * sin(v * 1.7 + t * 0.5)
                rgb = pal.cycle((v + 4.0) / 8.0 + t * 0.03)
                c.set(x, y, (rgb[0] * depth, rgb[1] * depth, rgb[2] * depth))

    def _retro_rainbow_tunnel(self, c: FxCanvas, t, pal: Palette):
        cx, cy = 15.5 + math.sin(t * 0.4) * 3, 3.5
        for y in range(HEIGHT):
            for x in range(WIDTH):
                dx, dy = (x - cx) / 4.0, y - cy
                dist = math.sqrt(dx * dx + dy * dy)
                angle = math.atan2(dy, dx)
                pulse = 0.5 + 0.5 * math.sin(dist * 4.2 - t * 3.0 + angle * 0.5)
                level = 0.06 + 0.94 * pulse * pulse
                rgb = pal.cycle(dist * 0.18 - t * 0.08)
                c.set(x, y, (rgb[0] * level, rgb[1] * level, rgb[2] * level))

    def _bit_invaders(self, c: FxCanvas, t, pal: Palette):
        for star in range(12):
            sx = (hash01(star, 1) * 40 - t * (0.6 + hash01(star, 2))) % 32
            sy = int(hash01(star, 3) * 8)
            twinkle = 0.02 + 0.03 * (0.5 + 0.5 * math.sin(t * 3 + star))
            c.dot(sx, sy, (twinkle, twinkle, twinkle * 1.4))
        march = (t * 5.0) % 48.0 - 8.0
        sprite = ALIEN if int(t * 2.5) % 2 == 0 else ALIEN_B
        bob = 0.5 * math.sin(t * 2.2)
        for slot, base_x in enumerate((march - 16, march, march + 16, march - 32)):
            rgb = pal.linear[slot % len(pal.linear)]
            for row, bits in enumerate(sprite):
                shade = 0.65 + 0.35 * (1 - row / 8)
                c.bitmap([bits], base_x, row + bob, (rgb[0] * shade, rgb[1] * shade, rgb[2] * shade), mode="add")

    def _neon_equalizer(self, c: FxCanvas, t, pal: Palette):
        def level(x, when):
            wave = math.sin(when * 2.5 + x * 0.55) + math.sin(when * 1.3 + x * 1.1) * 0.6
            wave += 0.4 * math.sin(when * 4.1 + x * 0.21)
            return max(0.6, min(8.0, (wave + 2.0) / 4.0 * 8.0))

        for x in range(WIDTH):
            height = level(x, t)
            # Analytic peak-hold: highest recent level, falling with gravity.
            peak = max(level(x, t - k * 0.06) - 9.0 * (k * 0.06) ** 2 for k in range(14))
            hue = pal.cycle(x / WIDTH * 0.9 + t * 0.02)
            for y in range(HEIGHT):
                fill = clamp01(height - (HEIGHT - 1 - y))
                if fill > 0:
                    lift = 0.35 + 0.65 * (HEIGHT - y) / HEIGHT
                    c.add(x, y, hue, fill * lift)
            peak_y = HEIGHT - peak
            if peak > height + 0.6:
                c.dot(x, max(0.0, peak_y - 0.5), (0.9, 0.9, 1.0), 0.85)

    def _matrix_rain(self, c: FxCanvas, t, pal: Palette):
        head_color = (0.75, 1.0, 0.8)
        for x in range(WIDTH):
            for drop in range(2):
                speed = 3.0 + hash01(x, drop, 11) * 4.0
                span = HEIGHT + 10 + hash01(x, drop, 12) * 12
                head = (t * speed + hash01(x, drop, 13) * span) % span - 3
                tail = 4 + hash01(x, drop, 14) * 5
                for y in range(HEIGHT):
                    behind = head - y
                    if behind < -0.5 or behind > tail:
                        continue
                    if behind < 0.5:
                        c.add(x, y, head_color, 1 - abs(behind) * 0.8)
                        continue
                    fade = (1 - behind / tail) ** 1.6
                    flicker = 0.85 + 0.15 * hash01(x, y, int(t * 8))
                    c.add(x, y, pal.ramp(0.35 + 0.55 * fade), fade * flicker)

    def _lava_lamp(self, c: FxCanvas, t, pal: Palette):
        blobs = [
            (8 + math.sin(t * 0.55) * 6, 3.5 + math.cos(t * 0.8) * 2.2),
            (19 + math.cos(t * 0.42) * 7, 3.5 + math.sin(t * 0.65) * 2.0),
            (27 + math.sin(t * 0.35 + 2) * 4, 3.5 + math.cos(t * 0.5) * 2.5),
            (14 + math.sin(t * 0.27 + 4) * 9, 3.5 + math.sin(t * 0.9 + 1) * 2.6),
        ]
        for y in range(HEIGHT):
            for x in range(WIDTH):
                energy = 0.0
                for bx, by in blobs:
                    energy += 2.2 / (((x - bx) / 2.4) ** 2 + (y - by) ** 2 + 0.8)
                body = smoothstep(0.75, 1.15, energy)
                glow = 0.06 * smoothstep(0.25, 0.75, energy)
                rgb = pal.ramp(0.45 + 0.5 * clamp01(energy / 3.0))
                amount = body * 0.95 + glow
                c.set(x, y, (rgb[0] * amount, rgb[1] * amount, rgb[2] * amount))

    def _pixel_snake(self, c: FxCanvas, t, pal: Palette):
        # A smooth Lissajous path replaces the old row-by-row serpentine.
        tail = 26
        for step in range(tail):
            when = t - step * 0.045
            x = 15.5 + 14.5 * math.sin(when * 0.9)
            y = 3.5 + 3.2 * math.sin(when * 1.7 + 0.6)
            fade = (1 - step / tail) ** 1.5
            c.dot(x, y, pal.cycle(step / tail * 0.6 + t * 0.05), fade * (1.4 if step == 0 else 0.75))
        food = int(t / 3)
        fx, fy = 2 + hash01(food, 1) * 27, 1 + hash01(food, 2) * 5
        c.glow(fx, fy, 1.2, to_linear(pal.bright), 0.5 + 0.3 * math.sin(t * 6))

    # ------------------------------------------------------------------ #
    # New presets
    # ------------------------------------------------------------------ #
    def _aurora(self, c: FxCanvas, t, pal: Palette):
        for star in range(9):
            sx, sy = int(hash01(star, 21) * 32), int(hash01(star, 22) * 4)
            twinkle = 0.012 + 0.02 * (0.5 + 0.5 * math.sin(t * (1 + hash01(star, 23) * 2) + star))
            c.add(sx, sy, (twinkle, twinkle, twinkle * 1.3))
        hem_color, top_color = pal.cycle(0.3), pal.cycle(0.68)
        for layer, (strength, offset, speed) in enumerate(((1.0, 0.0, 1.0), (0.55, 3.7, -0.7))):
            for x in range(WIDTH):
                # Slow folds along the curtain plus fine vertical rays.
                fold = fbm2(x * 0.08 + t * 0.05 * speed + offset, t * 0.04, 2, 5 + layer)
                curtain = smoothstep(0.3, 0.62, fold)
                if curtain <= 0.01:
                    continue
                ray = noise2(x * 0.85 + t * 0.5 * speed, t * 0.3 + layer * 4, 9 + layer)
                ray = 0.25 + 0.75 * ray * ray
                hem = 6.3 - layer * 1.4 + 1.1 * math.sin(x * 0.19 + t * 0.3 * speed + offset)
                height = 3.0 + 2.5 * fold
                column = strength * curtain * ray * 0.95
                hr, hg, hb = hem_color
                dr, dg, db = top_color[0] - hr, top_color[1] - hg, top_color[2] - hb
                for y in range(max(0, int(hem - height - 1)), min(HEIGHT, int(hem + 1.8))):
                    above = hem - y
                    if above < -0.8:
                        continue
                    # Soft lower hem (smoothstep), long fade towards the sky.
                    k = min(1.0, (above + 0.8) / 1.2)
                    edge = k * k * (3 - 2 * k)
                    fade = max(0.0, 1 - above / (height + 1)) ** 1.4
                    mix = min(1.0, max(0.0, above / height))
                    amount = column * edge * fade
                    i = y * WIDTH + x
                    c.r[i] += (hr + dr * mix) * amount
                    c.g[i] += (hg + dg * mix) * amount
                    c.b[i] += (hb + db * mix) * amount

    def _ripple(self, c: FxCanvas, t, pal: Palette):
        interval, life, speed = 0.75, 3.2, 6.0
        latest = math.floor(t / interval)
        drops = []
        for n in range(latest - int(life / interval), latest + 1):
            age = t - n * interval - hash01(n, 3) * 0.4
            if 0 <= age < life:
                drops.append((hash01(n, 1) * 31, hash01(n, 2) * 7, age))
        deep = pal.ramp(0.18)
        crest = pal.ramp(0.95)
        for y in range(HEIGHT):
            for x in range(WIDTH):
                wave = 0.0
                for dx, dy, age in drops:
                    distance = math.hypot(x - dx, (y - dy) * 1.15)
                    ring = distance - age * speed
                    if -2.5 < ring < 1.5:
                        wave += math.cos(ring * 2.2) * math.exp(-ring * ring * 0.6) * math.exp(-age * 1.1)
                base = 0.25 + 0.08 * math.sin(x * 0.3 + t * 0.6 + y * 0.5)
                lit = clamp01(wave)
                amount = base * (1 - lit) + lit
                color = (deep[0] + (crest[0] - deep[0]) * lit, deep[1] + (crest[1] - deep[1]) * lit,
                         deep[2] + (crest[2] - deep[2]) * lit)
                c.set(x, y, (color[0] * amount, color[1] * amount, color[2] * amount))
        for dx, dy, age in drops:
            if age < 0.18:
                c.glow(dx, dy, 1.1, to_linear(pal.bright), 1 - age / 0.18)

    def _fireflies(self, c: FxCanvas, t, pal: Palette):
        ground = pal.ramp(0.25)
        for x in range(WIDTH):
            sway = 0.5 + 0.5 * math.sin(x * 1.3 + t * 0.8)
            c.add(x, 7, ground, 0.08 + 0.05 * sway)
            if hash01(x, 41) > 0.55:
                c.add(x, 6, ground, 0.04 * sway)
        for fly in range(9):
            fx = 15.5 + 15 * math.sin(t * (0.11 + hash01(fly, 1) * 0.12) + fly * 2.1) * (0.6 + 0.4 * math.sin(t * 0.07 + fly))
            fy = 3.2 + 2.6 * math.sin(t * (0.23 + hash01(fly, 2) * 0.2) + fly * 1.3)
            period = 2.2 + hash01(fly, 3) * 2.5
            phase = ((t + hash01(fly, 4) * period) % period) / period
            pulse = 0.06 + 0.94 * math.sin(math.pi * clamp01(phase / 0.45)) ** 3 if phase < 0.45 else 0.06
            color = pal.ramp(0.7 + 0.3 * hash01(fly, 5))
            c.glow(fx, fy, 1.6, color, pulse * 0.9)
            c.dot(fx, fy, (color[0] * 1.2, color[1] * 1.2, color[2] * 1.2), pulse * 0.6)

    def _sine_ribbons(self, c: FxCanvas, t, pal: Palette):
        ribbons = [
            (2.6, 0.32, 1.10, 0.0, 0.00),
            (2.2, 0.21, -0.85, 2.1, 0.33),
            (1.8, 0.45, 0.60, 4.2, 0.66),
        ]
        for amplitude, freq, velocity, phase, hue_offset in ribbons:
            for x in range(WIDTH):
                centre = 3.5 + amplitude * math.sin(x * freq + t * velocity + phase) + 0.6 * math.sin(x * freq * 2.3 - t * 0.7)
                color = pal.cycle(hue_offset + x / 96 + t * 0.03)
                for y in range(max(0, int(centre) - 2), min(HEIGHT, int(centre) + 3)):
                    d = y - centre
                    core = math.exp(-d * d / 0.28)
                    halo = 0.12 * math.exp(-d * d / 2.5)
                    c.add(x, y, color, (core + halo) * 0.8)

    def _synthwave(self, c: FxCanvas, t, pal: Palette):
        horizon = 4
        sky_top, sky_low = pal.ramp(0.15), pal.ramp(0.45)
        for y in range(horizon):
            amount = y / max(1, horizon - 1)
            color = tuple(a + (b - a) * amount for a, b in zip(sky_top, sky_low))
            for x in range(WIDTH):
                c.set(x, y, (color[0] * 0.35, color[1] * 0.35, color[2] * 0.35))
        # Striped retro sun sinking into the horizon line.
        sun_x, sun_y, radius = 15.5, horizon + 0.3, 3.6
        stripe_shift = (t * 0.8) % 1.0
        for y in range(horizon):
            for x in range(9, 23):
                d = math.hypot((x - sun_x) * 0.9, y - sun_y)
                cover = 1 - smoothstep(radius - 0.6, radius + 0.4, d)
                if cover <= 0:
                    continue
                band = (sun_y - y + stripe_shift) % 1.6
                gap = y >= 2 and band < 0.45
                if gap:
                    continue
                c.over(x, y, pal.ramp(0.98 - 0.3 * (y / horizon)), cover)
        line_color = pal.ramp(0.8)
        for x in range(WIDTH):
            c.add(x, horizon, line_color, 0.9)
        # Perspective grid: rows approach the viewer, columns fan out.
        grid = pal.ramp(0.55)
        for y in range(horizon + 1, HEIGHT):
            near = y - horizon
            depth = 1.0 / (near + 0.35)
            z = (depth * 3.0 + t * 1.3) % 1.0
            row_glow = math.exp(-((min(z, 1 - z)) ** 2) / 0.012)
            for x in range(WIDTH):
                c.add(x, y, grid, row_glow * 0.55)
            spacing = near * 2.8
            for k in range(-6, 7):
                c.dot(15.5 + k * spacing, y, line_color, 0.18 + 0.14 * near)

    def _embers(self, c: FxCanvas, t, pal: Palette):
        for x in range(WIDTH):
            heat = fbm2(x * 0.25, t * 0.7, 2, 31)
            for y in (5, 6, 7):
                depth = (y - 4) / 3
                level = clamp01(heat * 1.3 * depth - 0.15 + 0.1 * math.sin(t * 2 + x))
                c.add(x, y, pal.ramp(level * 0.8), level * 0.8)
        for spark in range(14):
            period = 2.2 + hash01(spark, 1) * 2.0
            age = (t + hash01(spark, 2) * period) % period
            life = age / period
            cycle = int((t + hash01(spark, 2) * period) / period)
            x = 2 + hash01(spark, cycle, 3) * 28 + math.sin(age * 3 + spark) * 1.2
            y = 7.2 - age * (2.5 + hash01(spark, 4) * 1.5)
            if y < -1:
                continue
            color = pal.ramp(1.0 - life * 0.7)
            c.dot(x, y, color, (1 - life) ** 1.3 * 1.2)

    def _game_of_life(self, c: FxCanvas, t, pal: Palette):
        rate = 3.0
        generation = max(0, int(t * rate))
        blend = ease_in_out_sine(t * rate - math.floor(t * rate))
        previous, current, ages = self._life_state(generation)
        for y in range(HEIGHT):
            for x in range(WIDTH):
                i = y * WIDTH + x
                was, now = previous[i], current[i]
                if not was and not now:
                    continue
                amount = 1.0 if was and now else blend if now else 1 - blend
                color = pal.cycle(0.1 + min(ages[i], 12) / 16)
                c.add(x, y, color, amount * 0.85)

    def _life_state(self, generation: int):
        epoch_length = 90
        epoch = generation // epoch_length
        target = generation % epoch_length
        state = self._life_cache
        if state.get("epoch") != epoch or state.get("step", 0) > target:
            grid = [1 if hash01(i, epoch, 77) < 0.33 else 0 for i in range(WIDTH * HEIGHT)]
            state.clear()
            state.update(epoch=epoch, step=0, grid=grid, previous=grid[:], ages=[g for g in grid], history=[])
        while state["step"] < target:
            grid = state["grid"]
            nxt = [0] * (WIDTH * HEIGHT)
            ages = state["ages"]
            new_ages = [0] * (WIDTH * HEIGHT)
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    n = 0
                    for dy in (-1, 0, 1):
                        row = ((y + dy) % HEIGHT) * WIDTH
                        for dx in (-1, 0, 1):
                            if dx or dy:
                                n += grid[row + (x + dx) % WIDTH]
                    i = y * WIDTH + x
                    alive = n == 3 or (grid[i] and n == 2)
                    nxt[i] = 1 if alive else 0
                    new_ages[i] = ages[i] + 1 if alive else 0
            state["step"] += 1
            history = state["history"]
            signature = hash(tuple(nxt))
            if signature in history or sum(nxt) < 4:
                # Stagnant or extinct: sprinkle a few deterministic seeds.
                for k in range(10):
                    nxt[int(hash01(epoch, state["step"], k) * WIDTH * HEIGHT)] = 1
            history.append(signature)
            del history[:-6]
            state["previous"], state["grid"], state["ages"] = grid, nxt, new_ages
        return state["previous"], state["grid"], state["ages"]

    def _starfield(self, c: FxCanvas, t, pal: Palette):
        # Every 14 s a warp burst adds extra travel. Distance is integrated
        # analytically (cycles + smoothstep), so motion never jumps.
        period, extra = 14.0, 9.0
        cycle = (t % period) / period
        u = clamp01((cycle - 0.7) / 0.3)
        travelled = t + extra * (math.floor(t / period) + u * u * (3 - 2 * u))
        warp = extra * 6 * u * (1 - u) / (0.3 * period)  # d(extra)/dt
        for star in range(34):
            depth = 0.25 + 0.75 * hash01(star, 1)
            x = 33 - ((travelled * 4.0 * depth + hash01(star, 2) * 40) % 40)
            y = int(hash01(star, 3) * 8)
            brightness = depth ** 1.5
            color = pal.ramp(0.55 + 0.45 * depth)
            length = warp * depth * 1.4
            if length > 0.3:
                c.line(x, y, x + length, y, color, brightness * 0.7)
            c.dot(x, y, color, brightness)
