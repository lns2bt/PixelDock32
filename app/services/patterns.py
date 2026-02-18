from typing import Callable

Frame = list[list[int]]


def blank(width: int = 32, height: int = 8) -> Frame:
    return [[0 for _ in range(width)] for _ in range(height)]


def single_pixel(index: int, width: int = 32, height: int = 8) -> Frame:
    frame = blank(width, height)
    total = width * height
    idx = index % total
    y = idx // width
    x = idx % width
    frame[y][x] = 1
    return frame


def vertical_stripes(step: int, width: int = 32, height: int = 8) -> Frame:
    frame = blank(width, height)
    shift = step % 2
    for y in range(height):
        for x in range(width):
            if (x + shift) % 2 == 0:
                frame[y][x] = 1
    return frame


def panel_blocks(panel: int, width: int = 32, height: int = 8, panel_width: int = 8) -> Frame:
    frame = blank(width, height)
    start_x = (panel % (width // panel_width)) * panel_width
    for y in range(height):
        for x in range(start_x, min(start_x + panel_width, width)):
            frame[y][x] = 1
    return frame


def border(width: int = 32, height: int = 8) -> Frame:
    frame = blank(width, height)
    for x in range(width):
        frame[0][x] = 1
        frame[height - 1][x] = 1
    for y in range(height):
        frame[y][0] = 1
        frame[y][width - 1] = 1
    return frame


PATTERN_FACTORIES: dict[str, Callable[[int], Frame]] = {
    "pixel_walk": lambda tick: single_pixel(tick),
    "stripes": lambda tick: vertical_stripes(tick),
    "panel_walk": lambda tick: panel_blocks(tick),
    "border": lambda tick: border(),
}
