"""Five handcrafted, deterministic clocks for the 32 × 8 display."""

from datetime import datetime
import math

from .core import Canvas, Scene, perimeter, seconds, shade


AMBER = (245, 173, 65)
IVORY = (235, 222, 185)
GREEN = (95, 219, 103)
BLUE = (91, 185, 250)


def _second_track(canvas, now, color):
    """Sixty fixed cells, read left-to-right in two thirty-cell rows."""
    for index in range(60):
        level = 1 if index <= now.second else .09
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
    filled = int(seconds(now) / 60 * 4)
    for x, y in upper[filled:]:
        canvas.pixel(x, y, AMBER)
    for x, y in lower[:filled]:
        canvas.pixel(x, y, AMBER)
    canvas.pixel(27, 2 + now.second % 2, shade(AMBER, .7))
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
    canvas = Canvas()
    inscription = _roman(now.hour) + ':' + _roman(now.minute)
    cycle = (len(inscription) + 3) * 4
    # Subpixel cross-fading keeps the scroll smooth without changing the time.
    offset = (elapsed * 5) % cycle
    for repeat in range(2):
        for index, glyph in enumerate(inscription):
            tile = Canvas()
            tile.text(glyph, 0, 0, IVORY)
            position = 1 + index * 4 + repeat * cycle - offset
            left = math.floor(position)
            fraction = position - left
            for y in range(5):
                for x in range(3):
                    if tile.colors[y][x] is not None:
                        _glow(canvas, left + x, y + 1, shade(IVORY, 1 - fraction))
                        _glow(canvas, left + x + 1, y + 1, shade(IVORY, fraction))
    border = perimeter()
    head = int(now.second * len(border) / 60)
    for index, (x, y) in enumerate(border):
        canvas.pixel(x, y, shade(AMBER, .35 if index < head else .07))
    canvas.pixel(*border[head], (255, 245, 185))
    return canvas


def mechanical_flip(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    digits = now.strftime('%H%M')
    for index, x in enumerate((0, 6, 13, 19)):
        for y in range(6):
            canvas.pixel(x, y, shade(IVORY, .17))
            canvas.pixel(x + 4, y, shade(IVORY, .17))
        canvas.text(digits[index], x + 1, 0, IVORY)
        # The hinge and shutter are driven by wall time, not scene age.
        canvas.pixel(x, 2, AMBER)
        canvas.pixel(x + 4, 2, AMBER)
        if now.second == 0 and now.microsecond < 250_000:
            shutter = min(4, int(now.microsecond / 50_000))
            for dx in range(1, 4):
                canvas.pixel(x + dx, shutter, shade(IVORY, .3))
    canvas.pixel(11, 1, AMBER)
    canvas.pixel(11, 3, AMBER)
    canvas.text(f'{now.second:02d}', 25, 0, AMBER)
    _second_track(canvas, now, AMBER)
    return canvas


def botanical(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    canvas.clock(now, GREEN, x=0, y=0)
    growth = seconds(now) / 60
    height = 1 + int(growth * 5)
    soil = (116, 78, 43)
    for x in range(23, 32):
        canvas.pixel(x, 5, soil)
    for step in range(height):
        y = 5 - step
        canvas.pixel(27, y, GREEN)
        if step > 0:
            direction = -1 if step % 2 else 1
            canvas.pixel(27 + direction, y, shade(GREEN, .7))
            canvas.pixel(27 + 2 * direction, min(5, y + 1), shade(GREEN, .45))
    if now.second >= 45:
        for x, y in ((26, 0), (28, 0), (27, 1)):
            canvas.pixel(x, y, (244, 130, 175))
        canvas.pixel(27, 0, AMBER)
    _second_track(canvas, now, GREEN)
    return canvas


def binary_precision(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    for x, value, color in ((2, now.hour, AMBER),
                            (12, now.minute, GREEN),
                            (22, now.second, BLUE)):
        for dx in range(6):
            canvas.pixel(x + dx, 0, shade(color, .55))
        for row in range(6):
            bit = 5 - row
            level = 1 if value & (1 << bit) else .09
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
        render=sandglass,
    ),
    Scene(
        key='craft_roman_scroll', title='Roman scroll', style='Antique treadmill',
        description='True 24 hour time and minutes in Roman numerals; N means zero. The writing glides smoothly through the frame.',
        seconds='The bright dot runs clockwise from the top left along the fixed frame and follows the wall clock second, not the running time.',
        render=roman_scroll,
    ),
    Scene(
        key='craft_mechanical_flip', title='Flip Clock', style='Mechanical panels',
        description='Four framed number panels with gold hinges and a short folding effect at the change of minutes.',
        seconds='The two gold numbers on the right show 00-59; In addition, two fixed rows with 30 points each count the seconds.',
        render=mechanical_flip,
    ),
    Scene(
        key='craft_botanical', title='Minute Garden', style='Botanical growth',
        description='A green clock next to a seedling that grows every minute and finally blooms pink.',
        seconds='Two fixed rows of 30 points each count 00-59 (first point = 00). Growth and flowering follow the current wall clock minute.',
        render=botanical,
    ),
    Scene(
        key='craft_binary_precision', title='Binary precision', style='Lighting bit registers',
        description='Three binary registers: hours in gold on the left, minutes in green in the middle, seconds in blue on the right.',
        seconds='The right register shows the real second in binary: from top to bottom the weights 32, 16, 8, 4, 2, 1; bright bits are added.',
        render=binary_precision,
    ),
]
