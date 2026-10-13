"""Five deterministic milestone ceremonies for the 32 × 8 clock canvas."""

from datetime import datetime
import math

from .core import Canvas, Scene, event_progress, mix, shade


def _reveal(canvas, now, phase, color):
    """Wipe away the artwork beneath a clock, complete by the final fifth."""
    width = int(max(0.0, min(1.0, (phase - .55) / .25)) * 21)
    clock = Canvas()
    clock.clock(now, color)
    for x in range(5, 5 + width):
        for y in range(1, 7):
            canvas.colors[y][x] = clock.colors[y][x]
    return canvas


def event_sand_turn(now: datetime, elapsed: float) -> Canvas:
    """Amber grains leave a turning hourglass and settle into the time."""
    phase = event_progress(elapsed, 8.0)
    canvas = Canvas()
    amber = (245, 173, 57)
    brass = (124, 79, 30)
    angle = math.pi * min(1.0, phase / .35)
    cosine, sine = math.cos(angle), math.sin(angle)

    def turn(x, y, color):
        dx, dy = x - 15.5, y - 3.5
        canvas.pixel(round(15.5 + dx * cosine - dy * sine),
                     round(3.5 + dx * sine + dy * cosine), color)

    for x in range(11, 21):
        turn(x, 0, brass)
        turn(x, 7, brass)
    for y, left in enumerate((11, 12, 13, 15, 15, 13, 12, 11)):
        turn(left, y, brass)
        turn(31 - left, y, brass)
    transfer = max(0.0, min(1.0, (phase - .25) / .45))
    for row in range(3):
        for x in range(12 + row, 20 - row):
            if row / 3 >= transfer:
                turn(x, row + 1, shade(amber, .55 + row * .15))
            if row / 3 < transfer:
                turn(x, 6 - row, amber)
    for grain in range(9):
        x = 3 + grain * 3
        y = int(phase * 22 + grain * 5) % 8
        if x < 10 or x > 21:
            canvas.pixel(x, y, shade(amber, .22))
    if .3 < phase < .8:
        canvas.pixel(15 + int(phase * 20) % 2, 3 + int(phase * 27) % 3, amber)
    for x in range(int(phase * 32)):
        canvas.pixel(x, 7, shade(amber, .5))
    return _reveal(canvas, now, phase, (255, 211, 120))


def event_matrix_gate(now: datetime, elapsed: float) -> Canvas:
    """Digital rain parts around a symmetric emerald gateway."""
    phase = event_progress(elapsed, 7.5)
    canvas = Canvas()
    green = (52, 230, 111)
    tick = int(phase * 42)
    opening = int(min(1.0, phase / .7) * 15)
    for column in range(0, 32, 2):
        head = (tick + column * 3 + column // 4) % 13 - 2
        for tail in range(5):
            y = head - tail
            if abs(column - 15.5) >= opening:
                canvas.pixel(column, y, shade(green, .65 * (1 - tail / 5)))
    left, right = 15 - opening, 16 + opening
    for y in range(8):
        canvas.pixel(left, y, shade(green, .4 + .3 * ((y + tick) % 3 == 0)))
        canvas.pixel(right, y, shade(green, .4 + .3 * ((7 - y + tick) % 3 == 0)))
    for x in range(left, right + 1):
        canvas.pixel(x, 0, shade(green, .2))
        canvas.pixel(x, 7, shade(green, .2))
    # Scanline brackets remain outside the finished clock's reading area.
    for y in (2, 5):
        canvas.pixel(2, y, (123, 255, 174))
        canvas.pixel(29, y, (123, 255, 174))
    return _reveal(canvas, now, phase, (134, 255, 186))


def event_prism_bloom(now: datetime, elapsed: float) -> Canvas:
    """A faceted crystal opens into restrained spectral petals."""
    phase = event_progress(elapsed, 9.0)
    canvas = Canvas()
    spectrum = ((248, 91, 128), (248, 169, 73), (158, 225, 104),
                (65, 219, 220), (112, 135, 255), (209, 112, 239))
    radius = 1 + phase * 17
    for petal in range(6):
        angle = petal * math.pi / 3 + phase * .8
        for step in range(1, 16):
            distance = step * radius / 15
            x = round(15.5 + math.cos(angle) * distance)
            y = round(3.5 + math.sin(angle) * distance * .28)
            canvas.pixel(x, y, shade(spectrum[petal], .2 + step / 24))
    # Nested diamond facets give the opening bloom a crystal silhouette.
    for facet in range(3):
        extent = 2 + facet * 2 + int(phase * 5)
        for dx in range(-extent, extent + 1):
            dy = round((1 - abs(dx) / extent) * (facet + 1))
            color = shade(spectrum[(facet + int(phase * 6)) % 6], .55)
            canvas.pixel(16 + dx, 3 - dy, color)
            canvas.pixel(16 + dx, 4 + dy, color)
    for x in range(32):
        color = spectrum[min(5, x * 6 // 32)]
        canvas.pixel(x, 7, shade(color, .4))
    return _reveal(canvas, now, phase, (232, 226, 255))


def event_roman_seal(now: datetime, elapsed: float) -> Canvas:
    """An antique seal is struck, then opens to ordinary Arabic digits."""
    phase = event_progress(elapsed, 8.5)
    canvas = Canvas()
    gold = (219, 166, 76)
    wax = (139, 47, 54)
    radius = min(12, 2 + int(phase * 32))
    for x in range(16 - radius, 16 + radius):
        edge = abs(x - 15.5) / radius
        top = 0 if edge < .65 else (1 if edge < .9 else 2)
        canvas.pixel(x, top, wax)
        canvas.pixel(x, 7 - top, wax)
    # XII evokes a dial inscription, without replacing the final HH:MM.
    if phase < .65:
        ink = mix((71, 36, 28), gold, min(1.0, phase * 4))
        canvas.bitmap(('101', '101', '010', '101', '101'), 10, 1, ink)
        canvas.bitmap(('111', '010', '010', '010', '111'), 15, 1, ink)
        canvas.bitmap(('111', '010', '010', '010', '111'), 19, 1, ink)
    # Two stepped laurel branches frame the stamped face.
    for row in range(1, 7):
        x = 3 + abs(3 - row) // 2
        canvas.pixel(x, row, shade(gold, .7))
        canvas.pixel(31 - x, row, shade(gold, .7))
        if row % 2:
            canvas.pixel(x + 1, row - 1, shade(gold, .4))
            canvas.pixel(30 - x, row - 1, shade(gold, .4))
    for x in range(10, 23):
        canvas.pixel(x, 7, shade(gold, .35))
    return _reveal(canvas, now, phase, (246, 219, 156))


def event_star_alignment(now: datetime, elapsed: float) -> Canvas:
    """Orbiting points align into a quiet, luminous time constellation."""
    phase = event_progress(elapsed, 10.0)
    canvas = Canvas()
    blue = (116, 171, 255)
    stars = ((1, 1), (4, 6), (7, 0), (11, 7), (21, 0),
             (25, 7), (28, 1), (30, 5))
    for index, (x, y) in enumerate(stars):
        brightness = .25 + .2 * (1 + math.sin(phase * 8 + index * 1.7))
        canvas.pixel(x, y, shade(blue, brightness))
    settle = min(1.0, phase / .75)
    for index in range(7):
        angle = index * math.tau / 7 + (1 - settle) * math.tau
        orbit_x = 15.5 + 13 * math.cos(angle)
        orbit_y = 3.5 + 3 * math.sin(angle)
        target_x = 3 + index * 4
        target_y = 0 if index % 2 == 0 else 7
        x = round(orbit_x * (1 - settle) + target_x * settle)
        y = round(orbit_y * (1 - settle) + target_y * settle)
        canvas.pixel(x, y, (205, 223, 255))
        if phase < .55:
            canvas.pixel(x - 1, y, shade(blue, .25))
            canvas.pixel(x, y + 1, shade(blue, .25))
    return _reveal(canvas, now, phase, (207, 229, 255))


SCENES = [
    Scene(key='event_sand_turn', title='Die Sandwende', style='Bernstein-Sanduhr',
          description='Die Sanduhr dreht sich; goldene Körner geben die aktuelle Uhrzeit frei.',
          seconds='Fallende Körner und eine wachsende Sandspur begleiten den Übergang.',
          render=event_sand_turn, duration=8.0, events=('hour', 'half', 'quarter')),
    Scene(key='event_matrix_gate', title='Das Matrix-Tor', style='Smaragd-Digitalregen',
          description='Grüne Datenströme öffnen ein Tor zur aktuellen Uhrzeit.',
          seconds='Ein wandernder Scan und fallende Pixel markieren die Öffnung.',
          render=event_matrix_gate, duration=7.5, events=('hour', 'half')),
    Scene(key='event_prism_bloom', title='Die Prismenblüte', style='Spektrale Kristallkunst',
          description='Ein facettierter Kristall entfaltet Farbblätter und enthüllt die Uhrzeit.',
          seconds='Strahlen und Diamantfacetten wachsen während der Zeremonie.',
          render=event_prism_bloom, duration=9.0, events=('hour', 'half', 'quarter')),
    Scene(key='event_roman_seal', title='Das römische Siegel', style='Antikes Wachs und Gold',
          description='Ein Siegel mit XII und Lorbeer öffnet sich zur heutigen Uhrzeit in HH:MM.',
          seconds='Der Siegelrand wächst; ein goldener Wisch legt die Ziffern frei.',
          render=event_roman_seal, duration=8.5, events=('hour', 'half')),
    Scene(key='event_star_alignment', title='Die Sternenordnung', style='Blaue Pixel-Astronomie',
          description='Sterne verlassen ihre Umlaufbahnen und rahmen die aktuelle Uhrzeit.',
          seconds='Sieben Lichtpunkte ziehen auf ruhigen Bahnen an den Bildrand.',
          render=event_star_alignment, duration=10.0, events=('hour', 'quarter')),
]
