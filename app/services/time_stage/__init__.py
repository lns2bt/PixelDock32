"""Time-Stage scene library. Scheduling and sleep policy belong to step two."""

import math

from . import chromatic, craft, cyber, events_arcade, events_art, retro, showcase, worlds
from .core import DIGIT_STYLE, DIGIT_STYLES

NORMAL_SCENES = tuple(retro.SCENES + chromatic.SCENES + cyber.SCENES + craft.SCENES) + worlds.SCENES + tuple(showcase.SCENES)
EVENT_SCENES = tuple(events_arcade.SCENES + events_art.SCENES)
SCENES = {scene.key: scene for scene in NORMAL_SCENES + EVENT_SCENES}


def render_scene(key, now, elapsed=0.0, digit_style=None):
    """Render one stateless scene, never touching hardware, storage or scheduling.

    ``digit_style`` overrides the scene's own digit-change style (``auto``/None
    keeps the scene default).
    """
    if key not in SCENES:
        raise ValueError('Unknown time stage scene')
    elapsed = float(elapsed)
    if not math.isfinite(elapsed):
        raise ValueError('Invalid animation time')
    scene = SCENES[key]
    style = digit_style if digit_style in DIGIT_STYLES else scene.digit_style
    token = DIGIT_STYLE.set(style)
    try:
        return scene.render(now, max(0.0, elapsed)).payload(now, key)
    finally:
        DIGIT_STYLE.reset(token)


def catalog():
    return [dict(key=s.key, title=s.title, style=s.style, description=s.description,
                 seconds=s.seconds, duration=s.duration, events=list(s.events),
                 digit_style=s.digit_style, added=s.added)
            for s in NORMAL_SCENES + EVENT_SCENES]
