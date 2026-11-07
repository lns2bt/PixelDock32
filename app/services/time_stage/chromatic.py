"""Five smooth psychedelic, pop-art and neon miniature clock scenes."""

from datetime import datetime
import math

from .core import Canvas, Scene, mix, perimeter, seconds, shade


_PALETTE = ((255, 48, 122), (255, 174, 38), (147, 245, 61),
            (35, 224, 244), (99, 88, 255), (237, 58, 232))


def _spectrum(phase):
    position = (phase % 1.0) * len(_PALETTE)
    index = int(position)
    return mix(_PALETTE[index], _PALETTE[(index + 1) % len(_PALETTE)],
               position - index)


def _clock(canvas, now, color=(245, 240, 255)):
    # Quiet negative space keeps the tiny numerals legible amid saturated art.
    for y in range(1, 6):
        for x in range(6, 25):
            canvas.pixel(x, y, (5, 3, 13))
    canvas.clock(now, color=color)


def _kaleidoscope(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    minute = seconds(now) / 60.0
    for y in range(8):
        for x in range(32):
            # Fold both axes: the two small wings mirror one another exactly.
            dx = min(x, 31 - x) - 2.5
            dy = abs(y - 3.5)
            radius = math.hypot(dx, dy)
            angle = math.atan2(dy, dx)
            petals = .5 + .5 * math.cos(4 * angle - minute * math.tau)
            color = _spectrum(radius / 9 + minute + elapsed / 48)
            canvas.pixel(x, y, shade(color, .12 + .48 * petals))
    # A clockwise minute necklace is an unambiguous seconds indicator.
    ring = perimeter()
    position = minute * len(ring)
    for index, (x, y) in enumerate(ring):
        fraction = max(0.0, min(1.0, position - index))
        color = _spectrum(index / len(ring) + elapsed / 48)
        canvas.pixel(x, y, mix(shade(color, .08), color, fraction))
    _clock(canvas, now)
    return canvas


def _lava(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    level = seconds(now) / 60.0 * 8
    for y in range(8):
        for x in range(32):
            flow = math.sin(x * .48 + elapsed * .35)
            flow += math.cos(y * .9 - elapsed * .28 + x * .19)
            color = mix((151, 24, 235), (255, 103, 28), (flow + 2) / 4)
            canvas.pixel(x, y, shade(color, .08))
            if x < 6 or x > 25:
                # The lava's surface rises only with wall-clock seconds.
                coverage = max(0.0, min(1.0, level - (7 - y)))
                heat = .45 + .25 * (flow + 2) / 4
                canvas.pixel(x, y, mix(shade(color, .08),
                                       shade(color, heat), coverage))
    # Flowing hot bubbles live below, not on top of, the clock glyphs.
    for x in range(6, 26):
        heat = .25 + .25 * (1 + math.sin(x * .6 - elapsed * .45))
        canvas.pixel(x, 7, shade((255, 61, 83), heat))
    _clock(canvas, now, (255, 228, 178))
    return canvas


def _pop_art(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    second = seconds(now)
    # Six comic panels, read down the left wing, then down the right.
    for panel in range(6):
        x0 = 0 if panel < 3 else 26
        y0 = (panel % 3) * 3
        amount = max(0.0, min(1.0, (second - panel * 10) / 10))
        ink = _PALETTE[panel]
        for dy in range(2):
            for dx in range(6):
                cell = dy * 6 + dx
                coverage = max(0.0, min(1.0, amount * 12 - cell))
                paper = shade(ink, .09 if (dx + dy) % 2 else .18)
                canvas.pixel(x0 + dx, y0 + dy, mix(paper, ink, coverage))
    # Ben-Day dots and a two-tone headline frame are deliberately graphic.
    drift = .5 + .5 * math.sin(elapsed * .35)
    for x in range(6, 26):
        canvas.pixel(x, 0, mix((255, 61, 150), (255, 195, 40), drift))
        canvas.pixel(x, 7, (35, 215, 234) if x % 2 else (12, 62, 80))
    for x in range(6, 26, 2):
        canvas.pixel(x, 6, (68, 24, 83))
    _clock(canvas, now, (255, 244, 102))
    return canvas


def _prism(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    second = seconds(now)
    # Angular dispersed rays, rather than an animated wash of color.
    for y in range(1, 7):
        for x in range(6):
            band = (x + 2 * y) % 6
            brightness = .3 + .15 * math.sin(elapsed * .3 + band * .6)
            canvas.pixel(x, y, shade(_PALETTE[band], brightness))
            canvas.pixel(31 - x, 7 - y, shade(_PALETTE[band], brightness))
    # Exactly sixty spectral cells: top left-to-right, bottom right-to-left.
    rail = [(x, 0) for x in range(1, 31)]
    rail += [(x, 7) for x in range(30, 0, -1)]
    for index, (x, y) in enumerate(rail):
        color = _spectrum(index / 60)
        coverage = max(0.0, min(1.0, second - index))
        canvas.pixel(x, y, mix(shade(color, .07), color, coverage))
    _clock(canvas, now)
    # Disperse the clock itself into fixed vertical spectral bands.
    for y in range(1, 6):
        for x in range(6, 25):
            if canvas.colors[y][x] == (245, 240, 255):
                canvas.pixel(x, y, mix(_spectrum((x - 6) / 23),
                                       (255, 255, 255), .45))
    return canvas


def _neon_pulse(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    second = seconds(now)
    # A traveling oscilloscope crest follows real seconds, not scene age.
    crest = second / 60 * 32
    for x in range(32):
        distance = min(abs(x - crest), 32 - abs(x - crest))
        glow = math.exp(-distance * distance / 12)
        canvas.pixel(x, 0, shade((35, 232, 255), .08 + .75 * glow))
        canvas.pixel(31 - x, 7, shade((255, 47, 197), .08 + .75 * glow))
    # Split seconds digits are steady and explicit; only their halo breathes.
    breath = .15 + .08 * math.sin(elapsed * .7)
    for x0, color in ((0, (35, 232, 255)), (28, (255, 47, 197))):
        for y in range(1, 7):
            for x in range(x0, x0 + 4):
                canvas.pixel(x, y, shade(color, breath))
    canvas.ticker(now, '%S', 0, 2, (95, 247, 255), unit='second', positions=(0, 28),
                  colors=((95, 247, 255), (255, 116, 219)))
    _clock(canvas, now, (205, 255, 244))
    return canvas


SCENES = [
    Scene(key="chroma_kaleidoscope", title="Kaleidoscope", style="Psychedelic",
          description="Reflective colored flowers around a calm, bright clock.",
          seconds="The edge chain fills clockwise during the minute; "
                  "the flowering phase also follows the real seconds.",
          render=_kaleidoscope, digit_style='morph'),
    Scene(key="chroma_lava", title="Lava Lamp", style="Psychedelic",
          description="Purple-orange lava flows into two chambers next to the clock.",
          seconds="The lava level rises from the bottom with the real seconds "
                  "above and starts again every full minute.",
          render=_lava, digit_style='fade'),
    Scene(key="chroma_pop_art", title="Seconds Comic", style="Pop-Art",
          description="Six colorful comic fields, grid dots and a yellow clock.",
          seconds="Each field stands for ten seconds: first to the left from top to bottom "
                  "down, then right. The current field fills pixel by pixel.",
          render=_pop_art, digit_style='flip'),
    Scene(key="chroma_prism", title="Minute Prism", style="Spectral",
          description="Angular rainbow rays and spectrally colored numbers.",
          seconds="Sixty light cells count the real seconds: up "
                  "right, then down to the left.",
          render=_prism, digit_style='morph'),
    Scene(key="chroma_neon_pulse", title="Neon Pulse", style="Neon",
          description="Turquoise and pink light trails frame a mint-colored clock.",
          seconds="On the left is the second tens digit, on the right is the ones digit; "
                  "the light trails run through one round per minute in parallel.",
          render=_neon_pulse, digit_style='fade'),
]
