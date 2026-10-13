"""Preview-only milestone scenes: pure, deterministic 32 × 8 animations."""

from datetime import datetime
import math

from .core import Canvas, Scene, event_progress, shade


def _clock_pixels(now):
    canvas = Canvas()
    canvas.clock(now)
    return [(x, y) for y, row in enumerate(canvas.colors)
            for x, color in enumerate(row) if color is not None]


def _frame(now, elapsed, duration, color):
    progress = event_progress(elapsed, duration)
    canvas = Canvas()
    settled = progress >= .8 - 1e-12
    if settled:
        canvas.clock(now, color=color)
    return canvas, progress / .8, settled


def _ease(value):
    value = max(0.0, min(1.0, value))
    return 1 - (1 - value) ** 3


def fireworks(now: datetime, elapsed: float) -> Canvas:
    """Three small fireworks scatter sparks that become clock strokes."""
    color = (255, 190, 95)
    canvas, phase, settled = _frame(now, elapsed, 9.0, color)
    if settled:
        return canvas
    centers = ((5, 4), (16, 3), (27, 4))
    palette = ((255, 100, 130), (255, 205, 90), (110, 200, 255))
    for index, (cx, cy) in enumerate(centers):
        burst = max(0.0, min(1.0, (phase - index * .08) / .48))
        if burst < .2:
            y = 7 - int(burst / .2 * (7 - cy))
            canvas.pixel(cx, y, palette[index])
            canvas.pixel(cx, y + 1, shade(palette[index], .3))
        elif phase < .65:
            radius = (burst - .2) * 5
            for ray in range(8):
                angle = ray * math.tau / 8
                canvas.pixel(cx + math.cos(angle) * radius,
                             cy + math.sin(angle) * radius * .6,
                             shade(palette[index], 1 - burst * .65))
    if phase >= .3:
        gather = _ease((phase - .3) / .7)
        for index, (x, y) in enumerate(_clock_pixels(now)):
            cx, cy = centers[index % 3]
            angle = index * 2.4
            sx = cx + math.cos(angle) * 4
            sy = cy + math.sin(angle) * 2
            canvas.pixel(sx + (x - sx) * gather,
                         sy + (y - sy) * gather, color)
    return canvas


def coin_burst(now: datetime, elapsed: float) -> Canvas:
    """Golden coins fan out of a chest and settle into the current time."""
    color = (255, 210, 75)
    canvas, phase, settled = _frame(now, elapsed, 8.0, color)
    if settled:
        return canvas
    if phase < .55:
        canvas.bitmap(('11111', '10001', '11111'), 14, 5, (155, 95, 40))
    for coin in range(7):
        flight = (phase * 1.8 - coin * .065)
        if 0 <= flight <= 1:
            x = 16 + (coin - 3) * flight * 4
            y = 5 - 16 * flight * (1 - flight)
            canvas.pixel(x, y, color)
            if coin % 2 == 0:
                canvas.pixel(x, y + 1, (185, 125, 35))
    gather = _ease((phase - .25) / .75)
    if phase >= .25:
        for index, (x, y) in enumerate(_clock_pixels(now)):
            angle = index * 2.399 + phase * math.tau
            sx = 16 + math.cos(angle) * 14
            sy = 3.5 + math.sin(angle) * 3
            canvas.pixel(sx + (x - sx) * gather,
                         sy + (y - sy) * gather, color)
    return canvas


def level_up(now: datetime, elapsed: float) -> Canvas:
    """An experience bar charges, then a scanner unlocks the clock."""
    color = (125, 255, 150)
    canvas, phase, settled = _frame(now, elapsed, 7.0, color)
    if settled:
        return canvas
    charge = min(1.0, phase / .4)
    for x in range(2, 30):
        canvas.pixel(x, 7, color if x - 2 < charge * 28 else (20, 45, 25))
    if phase < .4:
        lift = int(charge * 2)
        canvas.bitmap(('00100', '01110', '10101'), 14, 3 - lift, color)
        canvas.pixel(16, 6 - lift, shade(color, .6))
    else:
        sweep = (phase - .4) / .6
        edge = 6 + sweep * 19
        for x, y in _clock_pixels(now):
            if x <= edge:
                canvas.pixel(x, y, color)
        if edge < 25:
            for y in range(1, 6):
                canvas.pixel(edge, y, (215, 255, 230))
        for side in (2, 28):
            canvas.pixel(side, 4 - int(sweep * 3), shade(color, .7))
            canvas.pixel(side - 1, 5 - int(sweep * 3), shade(color, .4))
            canvas.pixel(side + 1, 5 - int(sweep * 3), shade(color, .4))
    return canvas


def portal(now: datetime, elapsed: float) -> Canvas:
    """A narrow violet portal stretches a compressed clock into place."""
    color = (185, 160, 255)
    canvas, phase, settled = _frame(now, elapsed, 10.0, color)
    if settled:
        return canvas
    opening = _ease(phase)
    radius = 1 + opening * 14
    for step in range(24):
        angle = step * math.tau / 24
        canvas.pixel(15.5 + math.cos(angle) * radius,
                     3.5 + math.sin(angle) * 3.5,
                     shade((165, 90, 255), .45 + .3 * math.sin(angle + phase * 8)))
    stretch = _ease((phase - .15) / .85)
    if phase >= .15:
        for x, y in _clock_pixels(now):
            canvas.pixel(15.5 + (x - 15.5) * stretch, y, color)
    return canvas


def block_build(now: datetime, elapsed: float) -> Canvas:
    """Falling arcade blocks lock into the clock, one column at a time."""
    color = (95, 210, 255)
    canvas, phase, settled = _frame(now, elapsed, 8.0, color)
    if settled:
        return canvas
    pixels = _clock_pixels(now)
    columns = sorted({x for x, _ in pixels})
    for index, column in enumerate(columns):
        start = index / len(columns) * .65
        fall = max(0.0, min(1.0, (phase - start) / .35))
        if phase < start:
            continue
        offset = int(round((1 - _ease(fall)) * 8))
        for x, y in pixels:
            if x == column:
                canvas.pixel(x, y - offset, color if fall == 1 else (255, 175, 90))
        if fall < 1:
            canvas.pixel(column, 7, shade(color, .35))
    return canvas


SCENES = [
    Scene(
        key='event_fireworks', title='Stundenfeuerwerk', style='Partikel · Festlich',
        description='Drei kleine Feuerwerke formen die aktuelle Uhrzeit aus ihren Funken.',
        seconds='9 Sekunden Ereignis-Countdown; danach bleibt die Uhrzeit klar lesbar.',
        render=fireworks, duration=9.0, events=('hour',),
    ),
    Scene(
        key='event_coin_burst', title='Münzenregen', style='Spielhalle · Gold',
        description='Goldene Münzen springen aus einer Truhe und sammeln sich zur Uhrzeit.',
        seconds='8 Sekunden Ereignis-Countdown mit ruhigem Uhrzeit-Finale.',
        render=coin_burst, duration=8.0, events=('half', 'hour'),
    ),
    Scene(
        key='event_level_up', title='Neue Stufe', style='Spielhalle · Aufstieg',
        description='Eine Erfahrungsleiste lädt sich auf und schaltet die aktuelle Uhrzeit frei.',
        seconds='7 Sekunden Ereignis-Countdown; die letzten 20 Prozent zeigen die Uhrzeit.',
        render=level_up, duration=7.0, events=('quarter', 'half', 'hour'),
    ),
    Scene(
        key='event_portal', title='Zeitportal', style='Portal · Violett',
        description='Ein violettes Portal öffnet sich und entfaltet die aktuelle Uhrzeit.',
        seconds='10 Sekunden Ereignis-Countdown mit anschließendem lesbarem Zeitbild.',
        render=portal, duration=10.0, events=('half', 'hour'),
    ),
    Scene(
        key='event_block_build', title='Zeitbausteine', style='Spielhalle · Bausteine',
        description='Fallende Bausteine setzen die aktuelle Uhrzeit Spalte für Spalte zusammen.',
        seconds='8 Sekunden Ereignis-Countdown; zum Schluss steht die Uhrzeit vollständig.',
        render=block_build, duration=8.0, events=('quarter', 'half', 'hour'),
    ),
]
