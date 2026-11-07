"""Five wall-clock-driven arcade scenes for a 32 × 8 pixel display."""

from datetime import datetime
import math

from .core import Canvas, Scene, perimeter, seconds, shade


def _platformer(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    tick = seconds(now)
    step = int(tick)
    gold = (255, 191, 40)
    brick = (177, 67, 36)

    # The uninterrupted clock is the level's score display.
    canvas.clock(now, (255, 228, 155), x=7)
    canvas.bitmap(('01110', '11100'), 0, 1, (240, 63, 51))
    canvas.bitmap(('01100', '11110'), 0, 3, (255, 175, 95))
    canvas.bitmap(('01110', '11001' if step % 2 else '01010'), 0, 5,
                  (73, 141, 255))

    # A coin spins once a second and bobs smoothly with the wall clock.
    coin_y = 1.5 - .5 * math.cos(tick * math.pi / 2)
    spin = abs(math.cos(tick * math.pi))
    coin = ('010', '111', '010') if spin > .45 else ('010', '010', '010')
    canvas.sprite(coin, 28, coin_y, gold)
    canvas.pixel(29, 5, shade(gold, .25))
    sparkle = max(0.0, 1 - (tick % 4) * 2)
    canvas.blend(27, 1, gold, .5 * sparkle)
    canvas.blend(31, 3, gold, .5 * sparkle)

    # The golden trail glides along the top edge over the real minute.
    head = tick * 32 / 60
    for x in range(32):
        canvas.pixel(x, 7, shade(brick, .8 if x % 4 else .35))
        canvas.pixel(x, 0, shade(gold, .35 * max(0.0, min(1.0, head - x))))
    canvas.dot(head, 0, gold)
    return canvas


_TETROMINOES = (
    (((0, 0), (1, 0), (2, 0), (1, 1)), (183, 92, 255)),
    (((0, 0), (1, 0), (0, 1), (1, 1)), (255, 213, 52)),
    (((1, 0), (2, 0), (0, 1), (1, 1)), (88, 235, 125)),
    (((0, 0), (0, 1), (1, 1), (2, 1)), (255, 139, 55)),
    (((0, 0), (1, 0), (2, 0), (3, 0)), (66, 225, 255)),
)


def _tetris(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    tick = seconds(now)
    palette = ((74, 226, 255), (188, 115, 255), (255, 198, 68), (95, 234, 144))
    # One calm digit colour keeps the time readable; colour lives in the wells.
    canvas.ticker(now, '%H:%M', 7, 1, (226, 234, 255), positions=(7, 11, 15, 19, 23))

    # Two tiny wells assemble and clear on a ten-second wall-clock cycle.
    for side, origin in enumerate((0, 28)):
        phase = (tick + side * 5) % 10
        rows = min(5, int(phase / 2))
        for row in range(rows):
            shape_color = _TETROMINOES[(int(tick / 10) + row + side) % 5][1]
            for column in range(4):
                canvas.pixel(origin + column, 6 - row,
                             shade(shape_color, .55 if column % 2 else .8))
        shape, color = _TETROMINOES[(int(tick / 2) + side) % 5]
        fall = (phase % 2) / 2
        fall_y = (fall * fall) * max(1, 5 - rows)
        for dx, dy in shape:
            canvas.dot(origin + dx, fall_y + dy, color)
        for column in range(4):
            canvas.pixel(origin + column, 7, (49, 64, 90))
    for x in range(7, 26):
        canvas.pixel(x, 7, shade(palette[(x // 4) % 4], .13))
    canvas.dot(7 + tick * 18 / 60, 7, (235, 245, 255))
    return canvas


def _invaders(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    tick = seconds(now)
    step = int(tick)
    green = (121, 255, 105)
    alien = ('10101', '01110', '11111', '10001' if step % 2 else '01010')
    canvas.bitmap(alien, 0, 1, green)
    canvas.bitmap(alien, 27, 1, (132, 189, 255))
    canvas.clock(now, (190, 255, 179), x=7)

    # A cannon patrols beneath the score; its shot stays outside the digits.
    cannon_x = 1 + tick * 28 / 60
    canvas.dot(cannon_x, 6, (225, 238, 255))
    canvas.sprite(('111',), cannon_x - 1, 7, (101, 185, 255))
    # One laser shot per second rises smoothly beside the score.
    shot = tick % 1
    canvas.dot(5 if step % 2 else 26, 6 - shot * 6, (255, 91, 122), 1 - shot * .5)
    for x in range(7, 26):
        canvas.pixel(x, 0, shade(green, .12))
    canvas.dot(7 + tick * 18 / 60, 0, green)
    # Fixed bunkers keep the bottom row recognizably arcade-like.
    for x in (4, 12, 20, 28):
        canvas.pixel(x, 7, shade(green, .38))
    return canvas


def _pac_maze(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    tick = seconds(now)
    blue = (45, 71, 210)
    gold = (255, 222, 43)
    route = perimeter()
    exact = tick * len(route) / 60
    position = int(exact) % len(route)

    for index, (x, y) in enumerate(route):
        if index % 2 == 0:
            canvas.pixel(x, y, (99, 83, 46))
    for x in (0, 5, 26, 31):
        for y in range(2, 6):
            canvas.pixel(x, y, shade(blue, .55))
    for x in (1, 2, 3, 4, 27, 28, 29, 30):
        canvas.pixel(x, 6, blue)

    ghost = ('010', '111', '101', '101' if int(tick) % 2 else '111')
    canvas.bitmap(ghost, 1, 2, (255, 86, 117))
    canvas.pixel(1, 3, (210, 234, 255))
    canvas.pixel(3, 3, (210, 234, 255))
    canvas.bitmap(('010', '101', '111'), 28, 2, (255, 106, 48))

    # The yellow runner eats a short trail, completing one lap each minute.
    for behind in range(1, 5):
        x, y = route[(position - behind) % len(route)]
        canvas.pixel(x, y, (0, 0, 0))
    x, y = route[position]
    canvas.track(route, exact, gold)
    inward_y = 1 if y == 0 else 6 if y == 7 else y
    inward_x = 1 if x == 0 else 30 if x == 31 else x
    canvas.pixel(inward_x, inward_y, gold)
    mouth = .5 + .5 * math.cos(tick * math.tau * 2)
    canvas.blend(inward_x + (1 if x < 16 else -1), inward_y, shade(gold, .7), mouth)
    # Paint the score last so a runner at the top cannot obscure the time.
    canvas.clock(now, (255, 239, 182), x=7)
    return canvas


def _cartridge(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    tick = seconds(now)
    amber = (255, 177, 54)
    phosphor = (133, 239, 191)
    # Eight full 3×5 characters fit exactly: HH:MM:SS occupies 31 columns.
    canvas.ticker(now, '%H:%M:%S', 0, 1, phosphor, unit='second',
                  colors=[phosphor] * 6 + [amber] * 2)
    for x in range(32):
        canvas.pixel(x, 0, shade(phosphor, .11 if x % 4 else .3))
        canvas.pixel(x, 7, shade(amber, .12 if x % 4 else .3))

    # Cartridge contacts encode the actual seconds, least significant first.
    for bit in range(6):
        color = amber if now.second & (1 << bit) else shade(amber, .15)
        canvas.pixel(2 + bit * 5, 6, color)
        canvas.pixel(3 + bit * 5, 6, color)
    canvas.dot(tick * 31 / 60, 0, phosphor)
    return canvas


SCENES = [
    Scene(
        key='retro_platformer', title='Coin Jump', style='Arcade platformer',
        description='Warm score clock over bricks, with running hero and golden coin.',
        seconds='The coin spins every second; the golden trail fills up every minute.',
        render=_platformer, digit_style='drop',
    ),
    Scene(
        key='retro_tetris', title='Block Time', style='Tetris Mosaic',
        description='A calm clock between two small, colourful, filling brick shafts.',
        seconds='Stones fall towards the wall clock; The setup starts again every ten seconds.',
        render=_tetris, digit_style='drop',
    ),
    Scene(
        key='retro_invaders', title='Star Defense', style='Space Arcade',
        description='Glowing alien guards flank the clock above a patrolling cannon.',
        seconds='Aliens change their legs every second; Cannon and point of light follow the minute.',
        render=_invaders, digit_style='decode',
    ),
    Scene(
        key='retro_pac_maze', title='Point hunter', style='Maze Arcade',
        description='A yellow runner chases edge points around a bright clock, ghost and bonus fruit.',
        seconds='The runner goes around the maze in a real minute and opens his mouth.',
        render=_pac_maze,
    ),
    Scene(
        key='retro_cartridge', title='Cartridge Chronometer', style='Retro Digital',
        description='Mint colored hours and minutes with amber seconds and module contacts.',
        seconds='HH:MM:SS shows real seconds; six pairs of contacts also form their binary value.',
        render=_cartridge,
    ),
]
