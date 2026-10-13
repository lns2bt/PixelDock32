"""Five wall-clock-driven arcade scenes for a 32 × 8 pixel display."""

from datetime import datetime

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

    # A coin flips once a second and bobs through four wall-clock phases.
    coin_y = 1 + (step % 4 in (1, 2))
    coin = ('010', '111', '010') if step % 2 == 0 else ('010', '010', '010')
    canvas.bitmap(coin, 28, coin_y, gold)
    canvas.pixel(29, 5, shade(gold, .25))
    if step % 4 == 0:
        canvas.pixel(27, 1, shade(gold, .5))
        canvas.pixel(31, 3, shade(gold, .5))

    head = int(tick * 32 / 60)
    for x in range(32):
        canvas.pixel(x, 7, shade(brick, .8 if x % 4 else .35))
        if x < head:
            canvas.pixel(x, 0, shade(gold, .35))
    canvas.pixel(head, 0, gold)
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
    for index, digit in enumerate(now.strftime('%H%M')):
        x = (7, 11, 19, 23)[index]
        canvas.text(digit, x=x, y=1, color=palette[index])
    canvas.text(':', x=15, y=1, color=(216, 224, 245))

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
        fall_y = int((phase % 2) * max(1, 5 - rows) / 2)
        for dx, dy in shape:
            canvas.pixel(origin + dx, fall_y + dy, color)
        for column in range(4):
            canvas.pixel(origin + column, 7, (49, 64, 90))
    for x in range(7, 26):
        canvas.pixel(x, 7, shade(palette[(x // 4) % 4], .13))
    canvas.pixel(7 + int(tick * 19 / 60), 7, (235, 245, 255))
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
    cannon_x = 1 + int(tick * 28 / 60)
    canvas.pixel(cannon_x, 6, (225, 238, 255))
    canvas.bitmap(('111',), cannon_x - 1, 7, (101, 185, 255))
    laser_y = 6 - step % 7
    canvas.pixel(5 if step % 2 else 26, laser_y, (255, 91, 122))
    for x in range(7, 26):
        canvas.pixel(x, 0, shade(green, .12))
    canvas.pixel(7 + int(tick * 19 / 60), 0, green)
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
    position = int(tick * len(route) / 60) % len(route)

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
    canvas.pixel(x, y, gold)
    inward_y = 1 if y == 0 else 6 if y == 7 else y
    inward_x = 1 if x == 0 else 30 if x == 31 else x
    canvas.pixel(inward_x, inward_y, gold)
    if int(tick * 4) % 2 == 0:
        canvas.pixel(inward_x + (1 if x < 16 else -1), inward_y, shade(gold, .7))
    # Paint the score last so a runner at the top cannot obscure the time.
    canvas.clock(now, (255, 239, 182), x=7)
    return canvas


def _cartridge(now: datetime, elapsed: float) -> Canvas:
    canvas = Canvas()
    tick = seconds(now)
    amber = (255, 177, 54)
    phosphor = (133, 239, 191)
    # Eight full 3×5 characters fit exactly: HH:MM:SS occupies 31 columns.
    canvas.text(now.strftime('%H:%M:%S'), x=0, y=1, color=phosphor)
    canvas.text(now.strftime('%S'), x=24, y=1, color=amber)
    for x in range(32):
        canvas.pixel(x, 0, shade(phosphor, .11 if x % 4 else .3))
        canvas.pixel(x, 7, shade(amber, .12 if x % 4 else .3))

    # Cartridge contacts encode the actual seconds, least significant first.
    for bit in range(6):
        color = amber if now.second & (1 << bit) else shade(amber, .15)
        canvas.pixel(2 + bit * 5, 6, color)
        canvas.pixel(3 + bit * 5, 6, color)
    canvas.pixel(int(tick * 32 / 60), 0, phosphor)
    return canvas


SCENES = [
    Scene(
        key='retro_platformer', title='Münzsprung', style='Arcade-Plattformer',
        description='Warme Punkteuhr über Backsteinen, mit laufendem Helden und goldener Münze.',
        seconds='Die Münze dreht sich jede Sekunde; die goldene Spur füllt sich pro Minute.',
        render=_platformer,
    ),
    Scene(
        key='retro_tetris', title='Bausteinzeit', style='Tetris-Mosaik',
        description='Vier farbige Ziffern zwischen zwei kleinen, sich füllenden Bausteinschächten.',
        seconds='Steine fallen nach der Wanduhr; alle zehn Sekunden beginnt der Aufbau neu.',
        render=_tetris,
    ),
    Scene(
        key='retro_invaders', title='Sternenabwehr', style='Weltraum-Arcade',
        description='Leuchtende Alienwachen flankieren die Uhr über einer patrouillierenden Kanone.',
        seconds='Aliens wechseln sekündlich ihre Beine; Kanone und Lichtpunkt folgen der Minute.',
        render=_invaders,
    ),
    Scene(
        key='retro_pac_maze', title='Punktejäger', style='Labyrinth-Arcade',
        description='Ein gelber Läufer jagt Randpunkte um eine helle Uhr, Geist und Bonusfrucht.',
        seconds='Der Läufer umrundet das Labyrinth in einer echten Minute und öffnet sein Maul.',
        render=_pac_maze,
    ),
    Scene(
        key='retro_cartridge', title='Modulchronometer', style='Retro-Digitalmodul',
        description='Mintfarbene Stunden und Minuten mit bernsteinfarbenen Sekunden und Modulkontakten.',
        seconds='HH:MM:SS zeigt echte Sekunden; sechs Kontaktpaare bilden zusätzlich deren Binärwert.',
        render=_cartridge,
    ),
]
