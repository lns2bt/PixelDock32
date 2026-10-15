"""Five tiny clock worlds: all motion is wall-time driven, digits stay untouched.

The central 19×5 rectangle (6..24, 1..5) is reserved, including digit gaps.
Everything else lives in the margins or the two-row animation lane below it.
"""
import math

from .core import Canvas, Scene, perimeter, seconds, shade

IVORY = (240, 235, 212)
ICE = (155, 225, 255)
TEAL = (65, 175, 185)
GREEN = (80, 190, 95)
AMBER = (230, 155, 55)


def _finish(canvas, now, color=IVORY):
    # Clear even the spaces around/between digits: decoration cannot mimic a glyph.
    for y in range(1, 6):
        for x in range(6, 25):
            canvas.colors[y][x] = None
    canvas.clock(now, color)
    return canvas


def _dot(canvas, track, position, color):
    """A subpixel head/trail remains smooth even on a short pixel track."""
    index = int(position) % len(track)
    fraction = position % 1
    canvas.pixel(*track[(index - 1) % len(track)], shade(color, .18))
    canvas.pixel(*track[index], shade(color, 1 - .6 * fraction))
    canvas.pixel(*track[(index + 1) % len(track)], shade(color, .4 * fraction))


def orbital_station(now, elapsed):
    canvas = Canvas(); s = seconds(now); track = perimeter()
    for index, point in enumerate(track):
        if index % 5 == 0: canvas.pixel(*point, shade(TEAL, .22))
    # Solar panels and the lit docking bay fit entirely beside the time.
    canvas.bitmap(('101', '111', '101'), 1, 2, shade(TEAL, .6))
    canvas.bitmap(('111', '010', '111'), 28, 2, shade(TEAL, .6))
    _dot(canvas, track, s / 60 * len(track), ICE)
    if s < 1:
        canvas.pixel(4, 3, shade(AMBER, .6 * (1 - s)))
        canvas.pixel(27, 3, shade(AMBER, .6 * (1 - s)))
    return _finish(canvas, now, ICE)


def greenhouse(now, elapsed):
    canvas = Canvas(); s = seconds(now)
    for x in range(32): canvas.pixel(x, 7, shade(GREEN, .15))
    for i, x in enumerate((2, 7, 12, 18, 24, 29)):
        growth = max(0, min(1, (s - i * 10) / 10))
        if growth > 0:
            canvas.pixel(x, 7, shade(GREEN, .4 + .4 * growth))
            canvas.pixel(x, 6, shade(GREEN, growth))
            if growth > .5: canvas.pixel(x + 1, 6, shade(GREEN, (growth - .5) * 1.4))
        if s < 1:
            canvas.pixel(x, 6, shade((245, 155, 185), .6 * (1 - s)))
    # Two larger seedlings at the edges make growth readable on only eight rows.
    canvas.bitmap(('010', '111', '010'), 1, 3, shade(GREEN, .35 + s / 120))
    canvas.bitmap(('010', '111', '010'), 28, 3, shade(GREEN, .35 + s / 120))
    canvas.pixel(1 + int(s) % 3, 2, shade(GREEN, .45))
    canvas.pixel(28 + int(s) % 3, 2, shade(GREEN, .45))
    _dot(canvas, [(x, 0) for x in range(32)], s / 60 * 32, (120, 195, 115))
    return _finish(canvas, now)


def neon_subway(now, elapsed):
    canvas = Canvas(); s = seconds(now)
    palettes = ((65, 180, 225), (220, 85, 180), (215, 160, 65))
    # A real minute picks the line, not the age of the current playlist visit.
    line_color = palettes[(now.hour * 60 + now.minute) % len(palettes)]
    for x in range(32): canvas.pixel(x, 7, shade(line_color, .18))
    for x in (1, 6, 12, 18, 24, 30): canvas.pixel(x, 7, shade(line_color, .55))
    head = int(s / 60 * 29)
    for offset in range(4):
        canvas.pixel(head + offset, 6, shade(line_color, .9 if offset != 2 else .3))
    canvas.bitmap(('1111', '1001', '1111'), 1, 2, shade(line_color, .4))
    canvas.bitmap(('1111', '1001', '1111'), 27, 2, shade(line_color, .4))
    if s < 1:
        for x in (2, 3, 28, 29): canvas.pixel(x, 3, shade(AMBER, .65 * (1 - s)))
    # A sixty-step alternating signal complements the 32-pixel train track.
    canvas.pixel(2 + now.second % 2, 0, shade(line_color, .7))
    canvas.pixel(6 + now.second % 10 * 2, 0, shade(line_color, .4))
    return _finish(canvas, now)


def lighthouse(now, elapsed):
    canvas = Canvas(); s = seconds(now)
    canvas.bitmap(('0110', '1111', '0110', '0110', '1111'), 1, 1, shade(IVORY, .55))
    canvas.pixel(2, 4, shade(AMBER, .7)); canvas.pixel(3, 4, shade(AMBER, .7))
    for x in range(32):
        canvas.pixel(x, 7, shade(TEAL, .2 + .12 * math.sin(x * .6 + s * 1.4)))
    coast = [(x, 6) for x in range(32)]
    _dot(canvas, coast, s / 60 * 31, (90, 180, 215))
    pulse = max(0, 1 - (s % 10) / .8)
    for x in range(1, 6): canvas.pixel(x, 0, shade(AMBER, pulse * .55))
    canvas.bitmap(('101', '010'), 28, 2, shade(TEAL, .5))
    if s < 1:
        _dot(canvas, [(x, 7) for x in range(32)], s * 31, (100, 205, 220))
    return _finish(canvas, now)


def _gear(canvas, x, step, color):
    canvas.pixel(x + 1, 3, shade(color, .6))
    teeth = (((1, 1), (1, 5), (0, 3), (2, 3)),
             ((0, 2), (2, 2), (0, 4), (2, 4)))
    for dx, y in teeth[step % 2]: canvas.pixel(x + dx, y, color)


def clockwork_factory(now, elapsed):
    canvas = Canvas(); s = seconds(now)
    _gear(canvas, 1, now.second, shade(AMBER, .7))
    _gear(canvas, 28, now.second + 1, shade((185, 125, 85), .7))
    for x in range(32):
        canvas.pixel(x, 7, shade(AMBER, .5 if x < int(s / 60 * 32) else .07))
    # The piston travels outside the digits and strokes on the minute boundary.
    piston = 1 + int((s if s < 1 else s % 1) * 3)
    for x in range(1, 5): canvas.pixel(x, 6, shade(TEAL, .35))
    canvas.pixel(piston, 6, shade(AMBER, .7))
    canvas.pixel(27 + (now.second % 4), 0, shade(AMBER, .45))
    return _finish(canvas, now)


SCENES = (
    Scene('world_orbital_station', 'Orbitalstation', 'Welten / Raumfahrt',
          'HH:MM als Kontrollzentrum mit Solarpaneelen und sanftem Andocklicht zum Minutenwechsel.',
          'Satellit umkreist den Rand in einer echten Minute.', orbital_station),
    Scene('world_greenhouse', 'Pixel-Gewächshaus', 'Welten / Natur',
          'Sechs kleine Pflanzen wachsen unter der ruhigen Uhr; zum Minutenbeginn kurze Blüten.',
          'Eine Pflanze je zehn Sekunden; Wanderlicht zeigt den Minutenfortschritt.', greenhouse),
    Scene('world_neon_subway', 'Neon-U-Bahn', 'Welten / Stadt',
          'Leuchtende Bahnhofsuhr, kleine Bahn und sechs Stationen; minutengesteuerte Linienfarben.',
          'Eine Fahrt pro Minute, Signal schaltet sekündlich, Türen leuchten zum Minutenbeginn.', neon_subway),
    Scene('world_lighthouse', 'Leuchtturm', 'Welten / Küste',
          'Warmweiße Uhr über einer dunklen Küstenlinie mit sanften Wellen und kleinem Leuchtfeuer.',
          'Küstenlicht wandert eine Minute; Lichtimpuls alle zehn Sekunden, Welle zum Minutenwechsel.', lighthouse),
    Scene('world_clockwork_factory', 'Uhrwerk-Manufaktur', 'Welten / Mechanik',
          'Messingzahnräder, Kupfer und ein kleiner Kolben rahmen die unverdeckte Uhrzeit.',
          'Zahnräder schalten sekündlich, die untere Leiste füllt sich pro Minute.', clockwork_factory),
)
