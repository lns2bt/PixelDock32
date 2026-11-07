"""Five handcrafted, deterministic clocks for the 32 × 8 display."""

from datetime import datetime
import math

from .core import Canvas, Scene, mix, perimeter, seconds, shade


AMBER = (245, 173, 65)
IVORY = (235, 222, 185)
GREEN = (95, 219, 103)
BLUE = (91, 185, 250)


def _second_track(canvas, now, color):
    """Sixty fixed cells, read left-to-right in two thirty-cell rows.

    The current cell lights up smoothly during its second.
    """
    current = seconds(now)
    for index in range(60):
        level = .09 + .91 * max(0.0, min(1.0, (current - index) * 3 + 1))
        canvas.pixel(1 + index % 30, 6 + index // 30, shade(color, level))


def sandglass(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    canvas.clock(now, AMBER, x=0, y=0)
    # A six-row vessel: upper grains drain into the lower bowl each minute.
    for y, left, right in ((0, 24, 30), (1, 25, 29), (2, 26, 28),
                           (3, 26, 28), (4, 25, 29), (5, 24, 30)):
        canvas.pixel(left, y, IVORY)
        canvas.pixel(right, y, IVORY)
    for x in range(24, 31):
        canvas.pixel(x, 0, IVORY)
        canvas.pixel(x, 5, IVORY)
    upper = ((26, 1), (27, 1), (28, 1), (27, 2))
    lower = ((26, 4), (27, 4), (28, 4), (27, 3))
    level = seconds(now) / 60 * 4
    for index, (x, y) in enumerate(upper):
        canvas.blend(x, y, AMBER, max(0.0, min(1.0, index + 1 - level)))
    for index, (x, y) in enumerate(lower):
        canvas.blend(x, y, AMBER, max(0.0, min(1.0, level - index)))
    # A grain falls through the neck every second, smoothly.
    grain = seconds(now) % 1
    canvas.dot(27, 2 + grain * 1.6, shade(AMBER, .9), 1 - grain * .3)
    _second_track(canvas, now, AMBER)
    return canvas


def _roman(value):
    if value == 0:
        return 'N'
    result = ''
    for number, glyph in ((50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'),
                          (5, 'V'), (4, 'IV'), (1, 'I')):
        count, value = divmod(value, number)
        result += glyph * count
    return result


def _glow(canvas, x, y, color):
    if 1 <= x <= 30 and 1 <= y <= 5:
        previous = canvas.colors[y][x] or (0, 0, 0)
        canvas.pixel(x, y, tuple(max(a, b) for a, b in zip(previous, color)))


def roman_scroll(now: datetime, elapsed: float) -> Canvas:
    """Hours (ivory) and minutes (amber) alternate, each centred and still."""
    canvas = Canvas()
    phase = seconds(now) % 8 / 8          # 4 s hours, 4 s minutes
    showing_hours = phase < .5
    local = (phase % .5) / .5
    # Short slide + fade between the two words; mostly perfectly still.
    enter = min(1.0, local / .12)
    leave = max(0.0, (local - .88) / .12)
    for word, color, active in ((_roman(now.hour), IVORY, showing_hours),
                                (_roman(now.minute), AMBER, not showing_hours)):
        if not active:
            continue
        width = len(word) * 4 - 1
        x0 = (32 - width) // 2
        offset = (1 - enter) * 3 - leave * 3
        alpha = min(enter, 1 - leave)
        tile = Canvas()
        tile.text(word, 0, 0, color)
        for y in range(5):
            for x in range(min(32, width)):
                if tile.colors[y][x] is not None:
                    canvas.dot(x0 + x, y + 1 + offset, color, alpha)
    # Hour/minute badge: left half of the top edge = hours, right half = minutes.
    for x in range(1, 31):
        hours_side = x < 16
        canvas.pixel(x, 0, shade(IVORY if hours_side else AMBER,
                                 .5 if hours_side == showing_hours else .08))
    border = perimeter()
    head = seconds(now) * len(border) / 60
    for index, (x, y) in enumerate(border):
        if y == 0 and 0 < x < 31:
            continue
        canvas.pixel(x, y, shade(AMBER, .35 if index < head else .07))
    canvas.track(border, head, (255, 245, 185))
    return canvas


def mechanical_flip(now: datetime, elapsed: float) -> Canvas:
    """Split-flap tiles: HH:MM on dark cards, amber seconds, minute bar below."""
    canvas = Canvas()
    for x0 in (0, 6, 13, 19):
        for y in range(7):
            for x in range(x0, x0 + 5):
                # Card face with a darker hinge line through the middle.
                canvas.pixel(x, y, shade(IVORY, .035 if y == 3 else .1))
    canvas.ticker(now, '%H:%M', 0, 1, IVORY, positions=(1, 7, 10, 14, 20))
    canvas.ticker(now, '%S', 0, 1, AMBER, unit='second', positions=(25, 29))
    filled = seconds(now) / 60 * 32
    for x in range(32):
        canvas.pixel(x, 7, mix(shade(AMBER, .08), shade(AMBER, .8), max(0.0, min(1.0, filled - x))))
    return canvas


def botanical(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    canvas.clock(now, GREEN, x=0, y=0)
    growth = seconds(now) / 60
    height = 1 + growth * 5
    soil = (116, 78, 43)
    for x in range(23, 32):
        canvas.pixel(x, 5, soil)
    for step in range(int(height) + 1):
        y = 5 - step
        amount = max(0.0, min(1.0, height - step))
        if amount <= 0:
            break
        canvas.blend(27, y, GREEN, amount)
        if step > 0:
            direction = -1 if step % 2 else 1
            canvas.blend(27 + direction, y, shade(GREEN, .7), amount)
            canvas.blend(27 + 2 * direction, min(5, y + 1), shade(GREEN, .45), amount)
    bloom = max(0.0, min(1.0, (seconds(now) - 45) / 3))
    if bloom > 0:
        for x, y in ((26, 0), (28, 0), (27, 1)):
            canvas.blend(x, y, (244, 130, 175), bloom)
        canvas.blend(27, 0, AMBER, bloom)
    _second_track(canvas, now, GREEN)
    return canvas


def binary_precision(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    from datetime import timedelta
    before = now - timedelta(seconds=1)
    fade = min(1.0, (now.microsecond / 1_000_000) / .3)
    for x, value, previous, color in ((2, now.hour, before.hour, AMBER),
                                      (12, now.minute, before.minute, GREEN),
                                      (22, now.second, before.second, BLUE)):
        for dx in range(6):
            canvas.pixel(x + dx, 0, shade(color, .55))
        for row in range(6):
            bit = 5 - row
            on, was = bool(value & (1 << bit)), bool(previous & (1 << bit))
            level = (1 if on else .09) if on == was else (.09 + .91 * fade if on else 1 - .91 * fade)
            for dx in range(4):
                canvas.pixel(x + dx, row + 1, shade(color, level))
            # Fixed reference marks delimit all six bit weights.
            canvas.pixel(x + 5, row + 1, shade(color, .22))
        for dx in range(4):
            canvas.pixel(x + dx, 7, shade(color, .3))
    return canvas


SCENES = [
    Scene(
        key='craft_sandglass', title='Hourglass', style='Golden sand',
        description='Digital hours and minutes next to an emptying hourglass.',
        seconds='Two fixed rows with 30 points each: Point 1 stands for second 00, point 60 for 59. The sand follows the real minute.',
        render=sandglass, digit_style='fade',
    ),
    Scene(
        key='craft_roman_scroll', title='Roman scroll', style='Antique treadmill',
        description='Hours (ivory) and minutes (amber) alternate in Roman numerals every four seconds; N means zero. The top edge shows which one is visible.',
        seconds='The bright dot runs clockwise from the top left along the fixed frame and follows the wall clock second, not the running time.',
        render=roman_scroll,
    ),
    Scene(
        key='craft_mechanical_flip', title='Flip Clock', style='Mechanical panels',
        description='Split-flap cards for hours and minutes that fold over at every change, plus amber seconds.',
        seconds='The amber numbers on the right show 00-59 and flip every second; the bottom bar fills over the minute.',
        render=mechanical_flip, digit_style='flip',
    ),
    Scene(
        key='craft_botanical', title='Minute Garden', style='Botanical growth',
        description='A green clock next to a seedling that grows every minute and finally blooms pink.',
        seconds='Two fixed rows of 30 points each count 00-59 (first point = 00). Growth and flowering follow the current wall clock minute.',
        render=botanical, digit_style='drop',
    ),
    Scene(
        key='craft_binary_precision', title='Binary precision', style='Lighting bit registers',
        description='Three binary registers: hours in gold on the left, minutes in green in the middle, seconds in blue on the right.',
        seconds='The right register shows the real second in binary: from top to bottom the weights 32, 16, 8, 4, 2, 1; bright bits are added.',
        render=binary_precision,
    ),
]
