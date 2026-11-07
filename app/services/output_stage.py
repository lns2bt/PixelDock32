"""Perceptual LED output stage (gamma + brightness-aware quantisation).

The Uno firmware (unchanged) scales every channel with
``out = (v * (brightness + 1)) >> 8`` before ``strip.show()``. WS2812 LEDs are
linear, the eye is not: without correction fades jump in the dark range and
mid-tones look washed out compared with the browser preview.

This stage runs on the Pi, *before* serial transfer. For each authored 8-bit
value it computes the physically desired output level after firmware scaling,
quantises that level once (optionally with temporal dithering) and inverts the
firmware formula to obtain the byte to send. Any lit authored pixel stays lit
(at least one output step on its brightest channel), so dim night scenes and
background accents never collapse to black at low brightness.

``gamma == 1`` without dithering bypasses the stage completely and reproduces
the previous behaviour byte-for-byte.
"""

from __future__ import annotations

import math


class OutputStage:
    def __init__(self, gamma: float = 2.2, temporal_dither: bool = False, min_visible: bool = True):
        self.gamma = max(1.0, min(3.0, float(gamma)))
        self.temporal_dither = bool(temporal_dither)
        self.min_visible = bool(min_visible)
        self._levels: dict[int, list[float]] = {}
        self._inverse: dict[int, list[int]] = {}
        self._error: dict[tuple[int, int], float] = {}

    @property
    def bypass(self) -> bool:
        return self.gamma == 1.0 and not self.temporal_dither

    @staticmethod
    def firmware_scale(value: int, brightness: int) -> int:
        """Exact replica of ``scaleChannelForBrightness`` in the Uno sketch."""
        if brightness >= 255:
            return value
        if brightness <= 0:
            return 0
        return (value * (brightness + 1)) >> 8

    @staticmethod
    def _max_level(brightness: int) -> int:
        return OutputStage.firmware_scale(255, brightness)

    def _level_table(self, brightness: int) -> list[float]:
        table = self._levels.get(brightness)
        if table is None:
            top = self._max_level(brightness)
            table = [((value / 255.0) ** self.gamma) * top for value in range(256)]
            self._levels[brightness] = table
        return table

    def _inverse_table(self, brightness: int) -> list[int]:
        """Smallest byte ``v`` whose firmware output equals each level."""
        table = self._inverse.get(brightness)
        if table is None:
            top = self._max_level(brightness)
            if brightness >= 255:
                table = list(range(256))
            else:
                scale = brightness + 1
                table = [min(255, math.ceil(level * 256 / scale)) for level in range(top + 1)]
            self._inverse[brightness] = table
        return table

    def apply(self, index_to_color: dict[int, tuple[int, int, int]], brightness: int | None) -> dict[int, tuple[int, int, int]]:
        if self.bypass:
            return index_to_color
        brightness = 255 if brightness is None else max(0, min(255, int(brightness)))
        if brightness <= 0:
            return index_to_color
        levels = self._level_table(brightness)
        inverse = self._inverse_table(brightness)
        top = len(inverse) - 1
        dither = self.temporal_dither
        errors = self._error
        out: dict[int, tuple[int, int, int]] = {}
        for index, rgb in index_to_color.items():
            targets = [levels[max(0, min(255, int(c)))] for c in rgb]
            if dither:
                quantised = []
                for channel, target in enumerate(targets):
                    key = (index, channel)
                    wanted = target + errors.get(key, 0.0)
                    level = max(0, min(top, int(wanted + 0.5)))
                    errors[key] = max(-0.5, min(0.5, wanted - level)) if target > 0 else 0.0
                    quantised.append(level)
            else:
                quantised = [min(top, int(t + 0.5)) for t in targets]
            if self.min_visible and not any(quantised) and any(rgb) and top > 0:
                # Keep the hue: light only the dominant channel(s) one step.
                peak = max(targets)
                quantised = [1 if t >= peak * 0.6 and t > 0 else 0 for t in targets]
            out[index] = (inverse[quantised[0]], inverse[quantised[1]], inverse[quantised[2]])
        if dither and len(errors) > 4096:
            errors.clear()
        return out
