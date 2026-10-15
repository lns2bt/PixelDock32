"""Time-Stage scene library. Scheduling and sleep policy belong to step two."""

import math

from . import chromatic, craft, cyber, events_arcade, events_art, retro, worlds

NORMAL_SCENES = tuple(retro.SCENES + chromatic.SCENES + cyber.SCENES + craft.SCENES) + worlds.SCENES
EVENT_SCENES = tuple(events_arcade.SCENES + events_art.SCENES)
SCENES = {scene.key: scene for scene in NORMAL_SCENES + EVENT_SCENES}


def render_scene(key, now, elapsed=0.0):
    """Render one stateless scene, never touching hardware, storage or scheduling."""
    if key not in SCENES:
        raise ValueError('Unbekannte Time-Stage-Szene')
    elapsed = float(elapsed)
    if not math.isfinite(elapsed):
        raise ValueError('Ungültige Animationszeit')
    scene = SCENES[key]
    return scene.render(now, max(0.0, elapsed)).payload(now, key)


def catalog():
    return [dict(key=s.key, title=s.title, style=s.style, description=s.description,
                 seconds=s.seconds, duration=s.duration, events=list(s.events))
            for s in NORMAL_SCENES + EVENT_SCENES]
