"""Shared float-colour effects toolkit for the 32 × 8 matrix.

Effects draw into :class:`FxCanvas`, which stores *linear light* floats
(0.0 … 1.0+, additive). Working in linear light makes glows, anti-aliased
sub-pixel motion and cross-fades physically plausible. ``to_colors()`` encodes
the buffer once into the regular 8-bit, perceptual ``color_frame`` used by the
rest of the application; the LED output stage then applies the panel gamma.

Everything here is pure, deterministic and cheap enough for a Raspberry Pi 3
at 30 FPS: no NumPy, no randomness without an explicit seed.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Sequence

WIDTH = 32
HEIGHT = 8
ENCODE_GAMMA = 2.2

RGB = tuple[int, int, int]
LinearRGB = tuple[float, float, float]

# --------------------------------------------------------------------------- #
# Colour transfer
# --------------------------------------------------------------------------- #

_DECODE = [((value / 255.0) ** ENCODE_GAMMA) for value in range(256)]
# Decision boundaries between neighbouring codes: exact, lossless round trips,
# including the darkest values that background art relies on.
_BOUNDS = [(_DECODE[i] + _DECODE[i + 1]) / 2 for i in range(255)]
# Fast path: a lookup table indexed in sqrt space (fine steps in the dark range).
_SQRT_STEPS = 8192
_SQRT_LUT = [bisect_right(_BOUNDS, (i / _SQRT_STEPS) ** 2) for i in range(_SQRT_STEPS + 1)]


def to_linear(color: Sequence[int]) -> LinearRGB:
    """8-bit perceptual colour → linear light."""
    return (_DECODE[_byte(color[0])], _DECODE[_byte(color[1])], _DECODE[_byte(color[2])])


def encode(value: float) -> int:
    """Linear light (clamped to 0…1) → 8-bit perceptual value."""
    if value <= 0.0:
        return 0
    if value >= 1.0:
        return 255
    return bisect_right(_BOUNDS, value)


def from_linear(color: Sequence[float]) -> RGB:
    return (encode(color[0]), encode(color[1]), encode(color[2]))


def _byte(value) -> int:
    value = int(value)
    return 0 if value < 0 else 255 if value > 255 else value


# --------------------------------------------------------------------------- #
# Easing & small maths
# --------------------------------------------------------------------------- #


def clamp01(value: float) -> float:
    return 0.0 if value <= 0.0 else 1.0 if value >= 1.0 else value


def smoothstep(edge0: float, edge1: float, value: float) -> float:
    if edge0 == edge1:
        return 0.0 if value < edge0 else 1.0
    t = clamp01((value - edge0) / (edge1 - edge0))
    return t * t * (3 - 2 * t)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease_linear(t: float) -> float:
    return clamp01(t)


def ease_in_out_sine(t: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * clamp01(t))


def ease_out_cubic(t: float) -> float:
    t = clamp01(t)
    return 1 - (1 - t) ** 3


def ease_in_cubic(t: float) -> float:
    return clamp01(t) ** 3


def ease_in_out_cubic(t: float) -> float:
    t = clamp01(t)
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_out_back(t: float, overshoot: float = 1.4) -> float:
    t = clamp01(t)
    c3 = overshoot + 1
    return 1 + c3 * (t - 1) ** 3 + overshoot * (t - 1) ** 2


EASINGS = {
    "linear": ease_linear,
    "sine": ease_in_out_sine,
    "cubic": ease_in_out_cubic,
    "out": ease_out_cubic,
    "in": ease_in_cubic,
    "back": ease_out_back,
}


# --------------------------------------------------------------------------- #
# Deterministic hashing & value noise
# --------------------------------------------------------------------------- #


def hash01(*values: int) -> float:
    """Stable integer hash → 0…1 (no global random state)."""
    h = 0x345678
    for value in values:
        h = (h ^ (int(value) & 0xFFFFFFFF)) * 0x01000193 & 0xFFFFFFFF
        h ^= h >> 15
        h = (h * 0x2C1B3C6D) & 0xFFFFFFFF
        h ^= h >> 12
    return (h & 0xFFFFFF) / float(0x1000000)


def _lattice(x: int, y: int, seed: int) -> float:
    """Cheap lattice hash for value noise (hot path; fixed arity)."""
    h = (x * 374761393 + y * 668265263 + seed * 2246822519) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFF) / 16777216.0


def noise2(x: float, y: float, seed: int = 0) -> float:
    """Smooth 2-D value noise in 0…1."""
    xi, yi = math.floor(x), math.floor(y)
    xf, yf = x - xi, y - yi
    u = xf * xf * (3 - 2 * xf)
    v = yf * yf * (3 - 2 * yf)
    a = _lattice(xi, yi, seed)
    b = _lattice(xi + 1, yi, seed)
    c = _lattice(xi, yi + 1, seed)
    d = _lattice(xi + 1, yi + 1, seed)
    return (a + (b - a) * u) + ((c + (d - c) * u) - (a + (b - a) * u)) * v


def fbm2(x: float, y: float, octaves: int = 3, seed: int = 0) -> float:
    total, amplitude, norm = 0.0, 1.0, 0.0
    for octave in range(octaves):
        total += noise2(x, y, seed + octave * 17) * amplitude
        norm += amplitude
        amplitude *= 0.5
        x *= 2.03
        y *= 2.03
    return total / norm


# --------------------------------------------------------------------------- #
# Gradients interpolated in OKLab (no muddy grey midpoints)
# --------------------------------------------------------------------------- #


def _linear_to_oklab(c: LinearRGB) -> tuple[float, float, float]:
    r, g, b = c
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    return (
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    )


def _oklab_to_linear(c: tuple[float, float, float]) -> LinearRGB:
    L, a, b = c
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        max(0.0, 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
        max(0.0, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
        max(0.0, -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s),
    )


def oklab_mix(a: Sequence[int], b: Sequence[int], t: float) -> RGB:
    """Perceptually even mix between two 8-bit colours."""
    la, lb = _linear_to_oklab(to_linear(a)), _linear_to_oklab(to_linear(b))
    t = clamp01(t)
    return from_linear(_oklab_to_linear(tuple(x + (y - x) * t for x, y in zip(la, lb))))


class Gradient:
    """Pre-sampled OKLab gradient returning *linear* colours.

    ``cyclic=True`` wraps the last stop back to the first one.
    """

    def __init__(self, stops: Sequence[Sequence[int]], cyclic: bool = False, samples: int = 256):
        if not stops:
            raise ValueError("gradient needs at least one colour")
        labs = [_linear_to_oklab(to_linear(stop)) for stop in stops]
        if cyclic:
            labs.append(labs[0])
        self.cyclic = cyclic
        self.samples = samples
        segments = max(1, len(labs) - 1)
        table: list[LinearRGB] = []
        for i in range(samples):
            position = i / (samples - 1 if not cyclic else samples) * segments
            index = min(segments - 1, int(position)) if len(labs) > 1 else 0
            frac = position - index if len(labs) > 1 else 0.0
            a = labs[index]
            b = labs[min(index + 1, len(labs) - 1)]
            table.append(_oklab_to_linear(tuple(x + (y - x) * frac for x, y in zip(a, b))))
        self._table = table

    def __call__(self, t: float) -> LinearRGB:
        if self.cyclic:
            t %= 1.0
        else:
            t = clamp01(t)
        index = int(t * (self.samples - 1) + 0.5) if not self.cyclic else int(t * self.samples) % self.samples
        return self._table[index]


def scale(color: Sequence[float], amount: float) -> LinearRGB:
    return (color[0] * amount, color[1] * amount, color[2] * amount)


# --------------------------------------------------------------------------- #
# Canvas
# --------------------------------------------------------------------------- #


class FxCanvas:
    """Additive linear-light canvas with anti-aliased sub-pixel primitives."""

    __slots__ = ("width", "height", "r", "g", "b")

    def __init__(self, width: int = WIDTH, height: int = HEIGHT):
        self.width = width
        self.height = height
        size = width * height
        self.r = [0.0] * size
        self.g = [0.0] * size
        self.b = [0.0] * size

    # -- construction ----------------------------------------------------- #
    @classmethod
    def from_colors(cls, color_frame, frame=None) -> "FxCanvas":
        canvas = cls(len(color_frame[0]) if color_frame else WIDTH, len(color_frame) or HEIGHT)
        for y, row in enumerate(color_frame):
            for x, rgb in enumerate(row):
                if rgb is None:
                    if frame is not None and frame[y][x]:
                        rgb = (80, 80, 80)
                    else:
                        continue
                elif frame is not None and not frame[y][x]:
                    continue
                i = y * canvas.width + x
                canvas.r[i], canvas.g[i], canvas.b[i] = to_linear(rgb)
        return canvas

    def copy(self) -> "FxCanvas":
        other = FxCanvas(self.width, self.height)
        other.r, other.g, other.b = self.r[:], self.g[:], self.b[:]
        return other

    # -- pixel access ----------------------------------------------------- #
    def get(self, x: int, y: int) -> LinearRGB:
        if 0 <= x < self.width and 0 <= y < self.height:
            i = y * self.width + x
            return (self.r[i], self.g[i], self.b[i])
        return (0.0, 0.0, 0.0)

    def set(self, x: int, y: int, color: Sequence[float]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            i = y * self.width + x
            self.r[i], self.g[i], self.b[i] = color[0], color[1], color[2]

    def add(self, x: int, y: int, color: Sequence[float], alpha: float = 1.0) -> None:
        if alpha <= 0.0 or not (0 <= x < self.width and 0 <= y < self.height):
            return
        i = y * self.width + x
        self.r[i] += color[0] * alpha
        self.g[i] += color[1] * alpha
        self.b[i] += color[2] * alpha

    def over(self, x: int, y: int, color: Sequence[float], alpha: float = 1.0) -> None:
        """Alpha-composite (normal blend) a colour on top of a pixel."""
        if alpha <= 0.0 or not (0 <= x < self.width and 0 <= y < self.height):
            return
        alpha = min(1.0, alpha)
        i = y * self.width + x
        keep = 1.0 - alpha
        self.r[i] = self.r[i] * keep + color[0] * alpha
        self.g[i] = self.g[i] * keep + color[1] * alpha
        self.b[i] = self.b[i] * keep + color[2] * alpha

    def lighten(self, x: int, y: int, color: Sequence[float], alpha: float = 1.0) -> None:
        if alpha <= 0.0 or not (0 <= x < self.width and 0 <= y < self.height):
            return
        i = y * self.width + x
        self.r[i] = max(self.r[i], color[0] * alpha)
        self.g[i] = max(self.g[i], color[1] * alpha)
        self.b[i] = max(self.b[i], color[2] * alpha)

    # -- whole-canvas operations ----------------------------------------- #
    def fill(self, color: Sequence[float]) -> None:
        size = self.width * self.height
        self.r = [color[0]] * size
        self.g = [color[1]] * size
        self.b = [color[2]] * size

    def fade(self, amount: float) -> None:
        self.r = [v * amount for v in self.r]
        self.g = [v * amount for v in self.g]
        self.b = [v * amount for v in self.b]

    def blend(self, other: "FxCanvas", amount: float) -> None:
        """Linear-light cross-fade towards ``other`` (0 = self, 1 = other)."""
        keep = 1.0 - amount
        self.r = [a * keep + b * amount for a, b in zip(self.r, other.r)]
        self.g = [a * keep + b * amount for a, b in zip(self.g, other.g)]
        self.b = [a * keep + b * amount for a, b in zip(self.b, other.b)]

    def composite(self, other: "FxCanvas", alpha: float = 1.0, mode: str = "add") -> None:
        for i in range(len(self.r)):
            r, g, b = other.r[i], other.g[i], other.b[i]
            if mode == "add":
                self.r[i] += r * alpha
                self.g[i] += g * alpha
                self.b[i] += b * alpha
            elif mode == "lighten":
                self.r[i] = max(self.r[i], r * alpha)
                self.g[i] = max(self.g[i], g * alpha)
                self.b[i] = max(self.b[i], b * alpha)
            elif mode == "screen":
                self.r[i] = 1 - (1 - min(1.0, self.r[i])) * (1 - min(1.0, r * alpha))
                self.g[i] = 1 - (1 - min(1.0, self.g[i])) * (1 - min(1.0, g * alpha))
                self.b[i] = 1 - (1 - min(1.0, self.b[i])) * (1 - min(1.0, b * alpha))
            else:  # over, using the brightest channel as coverage
                coverage = min(1.0, max(r, g, b) * 4) * alpha
                if coverage > 0:
                    keep = 1.0 - coverage
                    self.r[i] = self.r[i] * keep + r * alpha
                    self.g[i] = self.g[i] * keep + g * alpha
                    self.b[i] = self.b[i] * keep + b * alpha

    # -- anti-aliased primitives ----------------------------------------- #
    def dot(self, x: float, y: float, color: Sequence[float], alpha: float = 1.0) -> None:
        """Bilinear sub-pixel splat: smooth motion between pixel centres."""
        x0, y0 = math.floor(x), math.floor(y)
        fx, fy = x - x0, y - y0
        self.add(x0, y0, color, alpha * (1 - fx) * (1 - fy))
        self.add(x0 + 1, y0, color, alpha * fx * (1 - fy))
        self.add(x0, y0 + 1, color, alpha * (1 - fx) * fy)
        self.add(x0 + 1, y0 + 1, color, alpha * fx * fy)

    def glow(self, x: float, y: float, radius: float, color: Sequence[float], alpha: float = 1.0,
             x_stretch: float = 1.0) -> None:
        """Soft round light with smooth falloff (bokeh / firefly / sun)."""
        if radius <= 0:
            return
        reach = radius + 1.0
        x_reach = reach * x_stretch
        inv = 1.0 / (radius * radius)
        for py in range(max(0, int(y - reach)), min(self.height, int(y + reach) + 2)):
            dy = py - y
            for px in range(max(0, int(x - x_reach)), min(self.width, int(x + x_reach) + 2)):
                dx = (px - x) / x_stretch
                d2 = (dx * dx + dy * dy) * inv
                if d2 < 1.0:
                    falloff = (1.0 - d2)
                    self.add(px, py, color, alpha * falloff * falloff)

    def line(self, x0: float, y0: float, x1: float, y1: float, color: Sequence[float], alpha: float = 1.0) -> None:
        """Anti-aliased line built from sub-pixel splats (≈ constant energy)."""
        length = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, int(length * 2))
        weight = alpha * (length / steps if length else 1.0)
        for step in range(steps + 1):
            t = step / steps
            self.dot(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, color, min(alpha, weight))

    def hline_soft(self, y: float, x0: float, x1: float, color: Sequence[float], alpha: float = 1.0) -> None:
        y0 = math.floor(y)
        fy = y - y0
        for x in range(max(0, int(x0)), min(self.width, int(math.ceil(x1)))):
            self.add(x, y0, color, alpha * (1 - fy))
            self.add(x, y0 + 1, color, alpha * fy)

    def bitmap(self, rows: Sequence[str], x: float, y: float, color: Sequence[float], alpha: float = 1.0,
               mode: str = "over") -> None:
        """Draw a 1-bit sprite; fractional positions are anti-aliased."""
        whole_x, whole_y = float(x).is_integer(), float(y).is_integer()
        for dy, row in enumerate(rows):
            for dx, bit in enumerate(row):
                if bit != "1":
                    continue
                if whole_x and whole_y:
                    px, py = int(x) + dx, int(y) + dy
                    if mode == "add":
                        self.add(px, py, color, alpha)
                    else:
                        self.over(px, py, color, alpha)
                else:
                    self._splat(x + dx, y + dy, color, alpha, mode)

    def _splat(self, x: float, y: float, color, alpha, mode):
        x0, y0 = math.floor(x), math.floor(y)
        fx, fy = x - x0, y - y0
        for px, py, w in ((x0, y0, (1 - fx) * (1 - fy)), (x0 + 1, y0, fx * (1 - fy)),
                          (x0, y0 + 1, (1 - fx) * fy), (x0 + 1, y0 + 1, fx * fy)):
            if w <= 0:
                continue
            if mode == "add":
                self.add(px, py, color, alpha * w)
            else:
                self.over(px, py, color, alpha * w)

    # -- export ------------------------------------------------------------ #
    def to_colors(self, intensity: float = 1.0) -> list[list[RGB | None]]:
        lut, steps, sqrt = _SQRT_LUT, _SQRT_STEPS, math.sqrt

        def code(value):
            value *= intensity
            if value <= 0.0:
                return 0
            if value >= 1.0:
                return 255
            return lut[int(sqrt(value) * steps)]

        values = [(code(r), code(g), code(b)) for r, g, b in zip(self.r, self.g, self.b)]
        w = self.width
        return [[rgb if (rgb[0] or rgb[1] or rgb[2]) else None for rgb in values[y * w:(y + 1) * w]]
                for y in range(self.height)]

    def to_frames(self, intensity: float = 1.0):
        colors = self.to_colors(intensity)
        return [[0 if c is None else 1 for c in row] for row in colors], colors


# --------------------------------------------------------------------------- #
# Proportional 3×5 text (tight, readable numbers on 32 px)
# --------------------------------------------------------------------------- #

GLYPHS_3X5 = {
    "°": ["11", "11", "00", "00", "00"],
    "1": ["01", "11", "01", "01", "01"],
    ".": ["0", "0", "0", "0", "1"],
    ",": ["0", "0", "0", "1", "1"],
    ":": ["0", "1", "0", "1", "0"],
    " ": ["00", "00", "00", "00", "00"],
    "!": ["1", "1", "1", "0", "1"],
    "m": ["000", "110", "111", "101", "101"],
    "h": ["100", "100", "110", "101", "101"],
    "/": ["001", "001", "010", "100", "100"],
}


def glyph(char: str) -> list[str]:
    from app.services.rendering import FONT_3X5

    if char in GLYPHS_3X5:
        return GLYPHS_3X5[char]
    return FONT_3X5.get(char, FONT_3X5.get(char.upper(), FONT_3X5[" "]))


def text_width(text: str, spacing: int = 1) -> int:
    if not text:
        return 0
    return sum(len(glyph(c)[0]) for c in text) + spacing * (len(text) - 1)


def draw_text(canvas: FxCanvas, text: str, x: float, y: float, color: Sequence[float], alpha: float = 1.0,
              spacing: int = 1, colors: Sequence[Sequence[float]] | None = None,
              offsets: Sequence[float] | None = None, clip: tuple[int, int] | None = None) -> int:
    """Proportional text; optional per-char colours and vertical offsets.

    ``clip`` limits drawing to rows ``clip[0] <= y < clip[1]`` (odometer rolls).
    Returns the width that was drawn.
    """
    cursor = x
    for index, char in enumerate(text):
        rows = glyph(char)
        tint = colors[index] if colors and index < len(colors) else color
        dy_offset = offsets[index] if offsets and index < len(offsets) else 0.0
        for dy, row in enumerate(rows):
            for dx, bit in enumerate(row):
                if bit != "1":
                    continue
                py = y + dy + dy_offset
                if clip is not None:
                    # Fractional rows are faded at the clip edges.
                    py0 = math.floor(py)
                    frac = py - py0
                    for ry, weight in ((py0, 1 - frac), (py0 + 1, frac)):
                        if weight > 0 and clip[0] <= ry < clip[1]:
                            canvas.over(int(cursor + dx), ry, tint, alpha * weight)
                elif float(py).is_integer() and float(cursor).is_integer():
                    canvas.over(int(cursor + dx), int(py), tint, alpha)
                else:
                    canvas._splat(cursor + dx, py, tint, alpha, "over")
        cursor += len(rows[0]) + spacing
    return int(round(cursor - x - spacing)) if text else 0
