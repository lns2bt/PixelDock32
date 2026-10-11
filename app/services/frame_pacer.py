"""Absolute-deadline pacing without catch-up bursts after missed frames."""

import math


class FramePacer:
    def __init__(self, fps: int, started_at: float):
        if fps <= 0:
            raise ValueError("fps must be positive")
        self.period = 1 / fps
        self.deadline = started_at
        self.missed_deadlines = 0

    def next_delay(self, now: float) -> float:
        self.deadline += self.period
        if self.deadline < now:
            missed = math.floor((now - self.deadline) / self.period) + 1
            self.missed_deadlines += missed
            self.deadline += missed * self.period
        return max(0.0, self.deadline - now)
