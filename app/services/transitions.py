"""Module-change transitions rendered in linear light with easing.

All effects are pure functions of ``progress`` (0 → old image, 1 → new image),
so the browser preview, tests and LEDs agree exactly. Sub-pixel motion is
anti-aliased; nothing strobes or flashes the whole matrix.
"""

from __future__ import annotations

import math

from app.services.fx import (
    FxCanvas, clamp01, ease_in_out_cubic, ease_in_out_sine, hash01, smoothstep,
)

W, H = 32, 8

EFFECTS = {
    "fade": "Gentle fade",
    "dissolve": "Soft pixel dissolve",
    "slide": "Vertical slide",
    "push_left": "Push left",
    "push_right": "Push right",
    "wipe": "Soft wipe",
    "iris": "Iris",
    "morph": "Pixel morph",
    "glitch": "Glitch",
    "none": "Without",
}

# 8 × 8 Bayer matrix: evenly spread, non-diagonal reveal order for dissolve.
_BAYER = [
    [0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26],
    [12, 44, 4, 36, 14, 46, 6, 38], [60, 28, 52, 20, 62, 30, 54, 22],
    [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
    [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21],
]
_RANK = [[((_BAYER[y][x % 8] + 64 * hash01(x // 8, 7)) % 64) / 64 for x in range(W)] for y in range(H)]


def _copy(frame, colors):
    return [row[:] for row in frame], [row[:] for row in colors]


def render(effect: str, from_frame, from_colors, to_frame, to_colors, progress: float, direction: str = "down"):
    progress = clamp01(float(progress))
    if effect in ("up", "down"):
        effect, direction = "slide", effect
    if effect not in EFFECTS:
        effect = "fade"
    if progress <= 0.0:
        return _copy(from_frame, from_colors)
    if progress >= 1.0 or effect == "none":
        return _copy(to_frame, to_colors)
    old = FxCanvas.from_colors(from_colors, from_frame)
    new = FxCanvas.from_colors(to_colors, to_frame)
    renderer = _RENDERERS[effect]
    if effect == "slide":
        out = renderer(old, new, progress, direction)
    elif effect == "morph":
        out = _morph(old, new, progress, from_frame, to_frame)
    else:
        out = renderer(old, new, progress)
    return out.to_frames()


def _fade(old: FxCanvas, new: FxCanvas, p: float) -> FxCanvas:
    old.blend(new, ease_in_out_sine(p))
    return old


def _dissolve(old: FxCanvas, new: FxCanvas, p: float) -> FxCanvas:
    out = FxCanvas()
    span = 0.35
    for y in range(H):
        rank_row = _RANK[y]
        for x in range(W):
            start = rank_row[x] * (1 - span)
            amount = smoothstep(start, start + span, p)
            i = y * W + x
            keep = 1 - amount
            out.r[i] = old.r[i] * keep + new.r[i] * amount
            out.g[i] = old.g[i] * keep + new.g[i] * amount
            out.b[i] = old.b[i] * keep + new.b[i] * amount
    return out


def _sample(canvas: FxCanvas, x: float, y: float, out: list, wrap: bool = False):
    """Bilinear sample; outside the canvas is black."""
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = x - x0, y - y0
    r = g = b = 0.0
    for px, py, w in ((x0, y0, (1 - fx) * (1 - fy)), (x0 + 1, y0, fx * (1 - fy)),
                      (x0, y0 + 1, (1 - fx) * fy), (x0 + 1, y0 + 1, fx * fy)):
        if w <= 0 or not (0 <= px < W and 0 <= py < H):
            continue
        i = py * W + px
        r += canvas.r[i] * w
        g += canvas.g[i] * w
        b += canvas.b[i] * w
    out[0] += r
    out[1] += g
    out[2] += b


def _shift(old: FxCanvas, new: FxCanvas, dx_old: float, dy_old: float, dx_new: float, dy_new: float) -> FxCanvas:
    out = FxCanvas()
    acc = [0.0, 0.0, 0.0]
    for y in range(H):
        for x in range(W):
            acc[0] = acc[1] = acc[2] = 0.0
            _sample(old, x - dx_old, y - dy_old, acc)
            _sample(new, x - dx_new, y - dy_new, acc)
            i = y * W + x
            out.r[i], out.g[i], out.b[i] = acc
    return out


def _slide(old, new, p, direction="down"):
    offset = ease_in_out_cubic(p) * H
    if direction == "up":
        return _shift(old, new, 0, -offset, 0, H - offset)
    return _shift(old, new, 0, offset, 0, offset - H)


def _push_left(old, new, p):
    offset = ease_in_out_cubic(p) * W
    return _shift(old, new, -offset, 0, W - offset, 0)


def _push_right(old, new, p):
    offset = ease_in_out_cubic(p) * W
    return _shift(old, new, offset, 0, offset - W, 0)


def _wipe(old, new, p):
    softness = 5.0
    edge = ease_in_out_sine(p) * (W + softness) - softness / 2
    out = FxCanvas()
    for x in range(W):
        amount = 1 - smoothstep(edge - softness / 2, edge + softness / 2, x)
        # A faint highlight rides on the wipe edge.
        # Lit pixels on the wipe edge brighten briefly; black stays black.
        shine = 1 + max(0.0, 1 - abs(x - edge) / 2.0) * 0.8 * math.sin(math.pi * p)
        for y in range(H):
            i = y * W + x
            keep = 1 - amount
            out.r[i] = (old.r[i] * keep + new.r[i] * amount) * shine
            out.g[i] = (old.g[i] * keep + new.g[i] * amount) * shine
            out.b[i] = (old.b[i] * keep + new.b[i] * amount) * shine
    return out


def _iris(old, new, p):
    radius = ease_in_out_sine(p) * 13.0
    out = FxCanvas()
    for y in range(H):
        dy = (y - 3.5) * 2.2
        for x in range(W):
            distance = math.hypot((x - 15.5) * 0.55, dy)
            amount = 1 - smoothstep(radius - 1.6, radius + 0.4, distance)
            i = y * W + x
            keep = 1 - amount
            out.r[i] = old.r[i] * keep + new.r[i] * amount
            out.g[i] = old.g[i] * keep + new.g[i] * amount
            out.b[i] = old.b[i] * keep + new.b[i] * amount
    return out


def _lit(canvas: FxCanvas, frame):
    points = []
    for y in range(H):
        for x in range(W):
            i = y * W + x
            if canvas.r[i] + canvas.g[i] + canvas.b[i] > 0.0005:
                points.append((x, y, (canvas.r[i], canvas.g[i], canvas.b[i])))
    # Column-major order pairs pixels with their nearest horizontal partner.
    points.sort(key=lambda point: (point[0] + point[1] * 0.12, point[1]))
    return points


def _morph(old: FxCanvas, new: FxCanvas, p: float, from_frame=None, to_frame=None) -> FxCanvas:
    a, b = _lit(old, from_frame), _lit(new, to_frame)
    if not a or not b or len(a) + len(b) > 420:
        return _fade(old, new, p)
    out = FxCanvas()
    count = max(len(a), len(b))
    for index in range(count):
        ax, ay, ac = a[index * len(a) // count]
        bx, by, bc = b[index * len(b) // count]
        delay = hash01(index, 31) * 0.3
        t = ease_in_out_cubic((p - delay) / 0.7)
        x = ax + (bx - ax) * t
        # A gentle arc lifts travelling particles, more for longer journeys.
        lift = math.sin(math.pi * t) * min(2.5, abs(bx - ax) * 0.12)
        y = ay + (by - ay) * t - lift
        color = tuple(ca + (cb - ca) * t for ca, cb in zip(ac, bc))
        x0, y0 = math.floor(x), math.floor(y)
        fx, fy = x - x0, y - y0
        for px, py, w in ((x0, y0, (1 - fx) * (1 - fy)), (x0 + 1, y0, fx * (1 - fy)),
                          (x0, y0 + 1, (1 - fx) * fy), (x0 + 1, y0 + 1, fx * fy)):
            out.lighten(px, py, color, w ** 0.75)
    return out


def _glitch(old, new, p):
    step = int(p * 9)
    strength = math.sin(math.pi * p) ** 2
    out = FxCanvas()
    acc = [0.0, 0.0, 0.0]
    for y in range(H):
        jitter = (hash01(step, y, 3) - 0.5) * 5 * strength
        use_new = hash01(step, y, 5) < smoothstep(0.25, 0.75, p)
        source = new if use_new else old
        split = 0.7 * strength
        for x in range(W):
            i = y * W + x
            acc[0] = acc[1] = acc[2] = 0.0
            _sample(source, x - jitter - split, y, acc)
            red = acc[0]
            acc[0] = acc[1] = acc[2] = 0.0
            _sample(source, x - jitter + split, y, acc)
            blue = acc[2]
            acc[0] = acc[1] = acc[2] = 0.0
            _sample(source, x - jitter, y, acc)
            out.r[i], out.g[i], out.b[i] = red, acc[1], blue
        if strength > 0.4 and hash01(step, y, 9) > 0.86:
            # Thin dim scanline, never a full-frame flash.
            for x in range(W):
                out.add(x, y, (0.05, 0.12, 0.10), strength)
    return out


_RENDERERS = {
    "fade": _fade,
    "dissolve": _dissolve,
    "slide": _slide,
    "push_left": _push_left,
    "push_right": _push_right,
    "wipe": _wipe,
    "iris": _iris,
    "morph": _morph,
    "glitch": _glitch,
}
