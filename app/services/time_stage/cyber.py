"""Five deterministic cyber and space clocks for the 32 × 8 stage."""

from datetime import datetime
import math

from .core import Canvas, Scene, progress, seconds, shade


GREEN = (70, 245, 130)
CYAN = (85, 225, 255)
PURPLE = (185, 130, 255)


def _matrix(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    wall = seconds(now)
    # Fixed column seeds give different speeds without mutable state or RNG.
    for x in range(32):
        seed = (x * 17 + 11) % 29
        head = (elapsed * (1.2 + seed / 23) + seed) % 12
        for y in range(8):
            distance = (head - y) % 12
            if distance < 3:
                canvas.pixel(x, y, shade(GREEN, .16 * (1 - distance / 3)))

    digits = Canvas()
    digits.text(now.strftime('%H:%M:%S'), x=1, y=1, color=GREEN)
    # Only the start of each real second assembles; the time remains readable
    # even then because unfinished strokes keep a dim persistent silhouette.
    phase = wall % 1
    for y in range(1, 6):
        for x in range(32):
            color = digits.colors[y][x]
            if color is not None:
                delay = ((x * 3 + y * 7) % 17) / 100
                amount = .55 + .45 * max(0.0, min(1.0, (phase - delay) / .08))
                canvas.pixel(x, y, shade(color, amount))
    progress(canvas, now, shade(GREEN, .45))
    return canvas


def _radar(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    angle = seconds(now) / 60 * math.tau - math.pi / 2
    # The compact radar occupies its own panel, never covering HH:MM.
    for y in range(7):
        for x in range(22, 32):
            dx, dy = (x - 26.5) / 1.4, y - 3
            radius = math.hypot(dx, dy)
            if radius > 3.2:
                continue
            bearing = math.atan2(dy, dx)
            lag = (angle - bearing) % math.tau
            ring = abs(radius - 3) < .35 or abs(radius - 1.5) < .3
            base = .13 if ring or y == 3 else .025
            trail = .65 * max(0.0, 1 - lag / .85)
            canvas.pixel(x, y, shade(GREEN, base + trail))
    canvas.pixel(27, 3, CYAN)
    canvas.clock(now, color=GREEN, x=1)
    progress(canvas, now, shade(GREEN, .6))
    return canvas


def _orbit(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    phase = seconds(now) / 60 * math.tau - math.pi / 2
    # A flattened orbit wraps around, rather than through, the clock face.
    for index in range(96):
        angle = index / 96 * math.tau
        x = round(15.5 + 15 * math.cos(angle))
        y = round(3.5 + 3.5 * math.sin(angle))
        canvas.pixel(x, y, shade(PURPLE, .12))
    for index in range(14, -1, -1):
        angle = phase - index * .025
        x = round(15.5 + 15 * math.cos(angle))
        y = round(3.5 + 3.5 * math.sin(angle))
        canvas.pixel(x, y, shade(CYAN, .18 + .82 * (1 - index / 14)))
    canvas.clock(now, color=PURPLE, x=6)
    return canvas


def _starfield(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    # Three fixed depth groups drift at different speeds. Brightness changes
    # continuously, avoiding random twinkles and frame-wide flashes.
    for index in range(28):
        depth = index % 3
        x = (index * 13 + 5 - elapsed * (.35 + depth * .45)) % 32
        y = (index * 5 + index // 3) % 8
        brightness = .10 + .12 * (1 + math.sin(elapsed * .6 + index)) / 2
        canvas.pixel(x, y, shade(CYAN, brightness))
    canvas.text(now.strftime('%H:%M:%S'), x=1, y=1, color=(170, 215, 255))
    # A small comet on the bottom row also supplies the minute's second hand.
    head = seconds(now) / 60 * 32
    for index in range(6, -1, -1):
        canvas.pixel((head - index) % 32, 7, shade(PURPLE, .8 * (1 - index / 7)))
    return canvas


def _circuit(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    # Two separated traces with alternating little vias and branch stubs.
    for x in range(32):
        canvas.pixel(x, 0, shade(CYAN, .13))
        canvas.pixel(x, 7, shade(CYAN, .13))
    for x in (0, 5, 12, 19, 26, 31):
        canvas.pixel(x, 6, shade(PURPLE, .32))
        canvas.pixel(x, 7, shade(PURPLE, .45))
    for x in (0, 31):
        for y in range(1, 7):
            canvas.pixel(x, y, shade(CYAN, .13))
    # The scan goes out across the upper bus and returns on the lower bus.
    position = seconds(now) / 60 * 64
    for tail in range(8, -1, -1):
        step = int(position - tail) % 64
        x, y = (step, 0) if step < 32 else (63 - step, 7)
        canvas.pixel(x, y, shade(CYAN, .2 + .8 * (1 - tail / 8)))
    canvas.text(now.strftime('%H:%M:%S'), x=1, y=1, color=(105, 235, 215))
    return canvas


SCENES = [
    Scene(
        key='cyber_matrix',
        title='Matrix Rain',
        style='Matrix · Green',
        description='Quiet rain of code behind numbers that are briefly made up of pixels.',
        seconds='HH:MM:SS shows real seconds; the bottom bar fills up over the course of the minute.',
        render=_matrix,
    ),
    Scene(
        key='cyber_radar',
        title='Seconds Radar',
        style='Cyber · Radar',
        description='A green radar disk scans the field next to the easy-to-read clock.',
        seconds='The radar beam starts at the top at second 0 and rotates once per real minute; The seconds bar grows at the bottom.',
        render=_radar,
    ),
    Scene(
        key='cyber_orbit',
        title='Orbital Clock',
        style='Space · orbit',
        description='A cyan satellite draws a purple ellipse around the time.',
        seconds='The satellite is at the top at second 0 and orbits the clock clockwise once every real minute.',
        render=_orbit,
    ),
    Scene(
        key='cyber_starfield',
        title='Star Flight',
        style='Space · Starfield',
        description='Several quiet layers of stars slide past behind a bright digital clock.',
        seconds='HH:MM:SS shows real seconds; the small comet below passes through the line once a minute.',
        render=_starfield,
    ),
    Scene(
        key='cyber_circuit',
        title='Circuit Scan',
        style='Cyber ​​· Circuit',
        description='A gentle light pulse travels on two conductor tracks around the digital display.',
        seconds='HH:MM:SS shows real seconds; the pulse runs up in seconds 0-29 and back down in seconds 30-59.',
        render=_circuit,
    ),
]
