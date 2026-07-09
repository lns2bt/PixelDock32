import math
import time

from app.modules.base import ModuleBase, ModulePayload

WIDTH = 32
HEIGHT = 8

PRESETS = {
    "psychedelic_plasma",
    "retro_rainbow_tunnel",
    "bit_invaders",
    "neon_equalizer",
    "matrix_rain",
    "lava_lamp",
    "pixel_snake",
}

PALETTES: dict[str, list[tuple[int, int, int]]] = {
    "neon": [(255, 0, 180), (0, 240, 255), (120, 255, 0), (255, 220, 0), (140, 80, 255)],
    "rainbow": [(255, 0, 0), (255, 130, 0), (255, 255, 0), (0, 220, 70), (0, 170, 255), (100, 70, 255), (220, 0, 255)],
    "fire": [(80, 0, 0), (220, 24, 0), (255, 120, 0), (255, 220, 80), (255, 255, 190)],
    "ocean": [(0, 25, 80), (0, 100, 180), (0, 210, 220), (120, 255, 210), (220, 255, 255)],
    "matrix": [(0, 40, 0), (0, 150, 35), (70, 255, 100), (210, 255, 210)],
}

ALIEN = [
    "01100110",
    "11111111",
    "10111101",
    "11111111",
    "00111100",
    "01011010",
    "10000001",
    "01000010",
]


def _clamp(value: float, minimum: int = 0, maximum: int = 255) -> int:
    return max(minimum, min(maximum, int(round(value))))


def _blank() -> tuple[list[list[int]], list[list[tuple[int, int, int] | None]]]:
    return [[0 for _ in range(WIDTH)] for _ in range(HEIGHT)], [[None for _ in range(WIDTH)] for _ in range(HEIGHT)]


def _palette(name: object) -> list[tuple[int, int, int]]:
    return PALETTES.get(str(name).strip().lower(), PALETTES["neon"])


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    amount = max(0.0, min(1.0, amount))
    return tuple(_clamp(a[i] + (b[i] - a[i]) * amount) for i in range(3))


def _palette_color(colors: list[tuple[int, int, int]], value: float) -> tuple[int, int, int]:
    value %= 1.0
    scaled = value * len(colors)
    idx = int(scaled) % len(colors)
    return _mix(colors[idx], colors[(idx + 1) % len(colors)], scaled - int(scaled))


def _scale(color: tuple[int, int, int], intensity: float) -> tuple[int, int, int]:
    return tuple(_clamp(channel * intensity) for channel in color)


class AnimationsModule(ModuleBase):
    key = "animations"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        preset = str(settings.get("preset", "psychedelic_plasma")).strip().lower()
        if preset not in PRESETS:
            preset = "psychedelic_plasma"
        speed = max(0.1, min(5.0, float(settings.get("speed", 1.0))))
        intensity = max(0.1, min(1.0, float(settings.get("intensity", 0.8))))
        mirror_mode = str(settings.get("mirror_mode", "none")).strip().lower()
        if mirror_mode not in {"none", "horizontal", "vertical", "quad"}:
            mirror_mode = "none"
        colors = _palette(settings.get("palette", "neon"))
        t = time.monotonic() * speed

        renderer = getattr(self, f"_{preset}")
        frame, color_frame = renderer(t, colors, intensity, cache)
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

    def _psychedelic_plasma(self, t, colors, intensity, cache):
        frame, color_frame = _blank()
        for y in range(HEIGHT):
            for x in range(WIDTH):
                v = math.sin(x * 0.34 + t) + math.cos(y * 0.95 - t * 1.2) + math.sin((x + y) * 0.22 + t * 0.7)
                color_frame[y][x] = _scale(_palette_color(colors, (v + 3.0) / 6.0), intensity)
                frame[y][x] = 1
        return frame, color_frame

    def _retro_rainbow_tunnel(self, t, colors, intensity, cache):
        frame, color_frame = _blank()
        cx, cy = (WIDTH - 1) / 2, (HEIGHT - 1) / 2
        for y in range(HEIGHT):
            for x in range(WIDTH):
                dx, dy = (x - cx) / 4.0, y - cy
                dist = math.sqrt(dx * dx + dy * dy)
                pulse = (math.sin(dist * 4.2 - t * 3.0) + 1) / 2
                if pulse > 0.18:
                    frame[y][x] = 1
                    color_frame[y][x] = _scale(_palette_color(colors, dist * 0.18 - t * 0.08), intensity * (0.45 + pulse * 0.55))
        return frame, color_frame

    def _bit_invaders(self, t, colors, intensity, cache):
        frame, color_frame = _blank()
        offset = int(t * 6) % WIDTH - 7
        bob = int(math.sin(t * 2.0) > 0)
        for base_x in (offset - 16, offset, offset + 16):
            for y, row in enumerate(ALIEN):
                for x, pixel in enumerate(row):
                    sx, sy = base_x + x, y + bob
                    if pixel == "1" and 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
                        frame[sy][sx] = 1
                        color_frame[sy][sx] = _scale(colors[(x + y) % len(colors)], intensity)
        return frame, color_frame

    def _neon_equalizer(self, t, colors, intensity, cache):
        frame, color_frame = _blank()
        for x in range(WIDTH):
            wave = math.sin(t * 2.5 + x * 0.55) + math.sin(t * 1.3 + x * 1.1) * 0.6
            height = max(1, min(HEIGHT, int((wave + 1.6) / 3.2 * HEIGHT)))
            for y in range(HEIGHT - height, HEIGHT):
                level = (HEIGHT - y) / HEIGHT
                frame[y][x] = 1
                color_frame[y][x] = _scale(_palette_color(colors, x / WIDTH + level * 0.2), intensity * (0.45 + level))
        return frame, color_frame

    def _matrix_rain(self, t, colors, intensity, cache):
        frame, color_frame = _blank()
        for x in range(WIDTH):
            head = int((t * (1.5 + (x % 5) * 0.28) + x * 3) % (HEIGHT + 8)) - 4
            for trail in range(5):
                y = head - trail
                if 0 <= y < HEIGHT:
                    frame[y][x] = 1
                    color_frame[y][x] = _scale(colors[min(len(colors) - 1, 3 - min(trail, 3))], intensity * (1 - trail * 0.16))
        return frame, color_frame

    def _lava_lamp(self, t, colors, intensity, cache):
        frame, color_frame = _blank()
        blobs = [
            (8 + math.sin(t * 0.55) * 6, 3.5 + math.cos(t * 0.8) * 2.2),
            (19 + math.cos(t * 0.42) * 7, 3.5 + math.sin(t * 0.65) * 2.0),
            (27 + math.sin(t * 0.35 + 2) * 4, 3.5 + math.cos(t * 0.5) * 2.5),
        ]
        for y in range(HEIGHT):
            for x in range(WIDTH):
                energy = sum(6.0 / (((x - bx) / 2.8) ** 2 + (y - by) ** 2 + 1.0) for bx, by in blobs)
                if energy > 0.55:
                    frame[y][x] = 1
                    color_frame[y][x] = _scale(_palette_color(colors, energy * 0.13 + t * 0.03), intensity * min(1.0, energy / 2.2))
        return frame, color_frame

    def _pixel_snake(self, t, colors, intensity, cache):
        frame, color_frame = _blank()
        path = [(x, 0) for x in range(WIDTH)] + [(WIDTH - 1 - x, 1) for x in range(WIDTH)] + [(x, 2) for x in range(WIDTH)] + [(WIDTH - 1 - x, 3) for x in range(WIDTH)] + [(x, 4) for x in range(WIDTH)] + [(WIDTH - 1 - x, 5) for x in range(WIDTH)] + [(x, 6) for x in range(WIDTH)] + [(WIDTH - 1 - x, 7) for x in range(WIDTH)]
        head = int(t * 10) % len(path)
        for trail in range(28):
            x, y = path[(head - trail) % len(path)]
            frame[y][x] = 1
            color_frame[y][x] = _scale(_palette_color(colors, (trail / 28) + t * 0.05), intensity * (1 - trail / 34))
        return frame, color_frame
