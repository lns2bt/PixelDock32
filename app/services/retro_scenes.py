"""Original tiny arcade scenes, not reproductions of commercial game assets."""

import math

HERO = ["..aa..", ".aaaa.", ".bcbc.", "..bb..", ".dddd.", "..dd..", ".d..d."]
PALETTE = {"a": 0xF7C948, "b": 0xF4BFA0, "c": 0x172338, "d": 0x47D7C4}


def scene(name, tick):
    pixels = [0] * 256

    def dot(x, y, color):
        if 0 <= x < 32 and 0 <= y < 8:
            pixels[y * 32 + x] = color

    if name == "starship":
        for i in range(15):
            dot((i * 11 - tick) % 32, (i * 3) % 8, 0x243652 if i % 2 else 0x707AB8)
        for x, y in [(2, 3), (3, 2), (3, 3), (3, 4), (4, 3), (5, 3)]:
            dot(x, y, 0x47D7C4)
        dot((7 + tick * 2) % 32, 3, 0xF7C948)
        dot(1, 3, 0xEF7285 if tick % 2 else 0xF7C948)
    else:
        for x in range(32):
            dot(x, 7, 0x614176 if (x + tick) % 4 else 0xAC70A8)
        for x, y in [(24, 1), (30, 2), (17, 0)]:
            dot(x, y, 0x4D537E)
        if name == "rooftop_runner":
            hero_x = 3
            offset = -1 if tick % 16 in range(6, 11) else 0
            obstacle = (31 - tick) % 32
            for y in (5, 6):
                dot(obstacle, y, 0xA580F5)
                dot(obstacle + 1, y, 0x7352AF)
        else:
            hero_x = tick % 26
            offset = -1 if tick % 12 in range(4, 9) else 0
            for x in (12, 22):
                dot(x, 2, 0xF7C948)
                dot(x, 3, 0xFFEDA0 if tick % 2 else 0xF7C948)
            for x in range(19, 24):
                dot(x, 5, 0xB57858)
        for y, row in enumerate(HERO):
            for x, char in enumerate(row):
                if char != ".":
                    dx = 1 if y == 6 and tick % 2 else 0
                    dot(hero_x + x + dx, y + offset, PALETTE[char])
    return pixels


def seed_retro_assets(store):
    for key, name in [("rooftop_runner", "Rooftop Runner"), ("coin_quest", "Coin Quest"), ("starship", "Starship Patrol")]:
        path = store.path("demo_" + key)
        if not path.exists():
            # Stable IDs keep demos from being duplicated on every startup.
            import json
            frames = [{"pixels": scene(key, tick), "duration_ms": 100} for tick in range(32)]
            with path.open("x") as handle:
                json.dump({"name": name, "frames": frames}, handle, separators=(",", ":"))
