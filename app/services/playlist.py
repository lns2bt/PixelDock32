"""Boundary-based playlist: ordered slots, occasional interludes, due priorities."""

import math
import random


class Playlist:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.current = None
        self.started = 0.0
        self.deadline = 0.0
        self.cursor = 0
        self.regular_count = 0
        self.last_priority = {}
        self.visits = {}
        self.generation = 0
        self.slot_type = "regular"

    @staticmethod
    def identity(row):
        return row.get("id", row["key"])

    def select(self, rows, now):
        available = {self.identity(row): row for row in rows}
        if self.current in available and now < self.deadline:
            return available[self.current]
        if not rows:
            self.current = None
            return None
        due = []
        for row in rows:
            interval = (row.get("settings") or {}).get("priority_every", 45 if row["key"] == "clock" else 0)
            if interval and now - self.last_priority.get(self.identity(row), now) >= interval:
                due.append(row)
            self.last_priority.setdefault(self.identity(row), now)
        regular = [row for row in rows if not (row.get("settings") or {}).get("shuffle", False)]
        shuffled = [row for row in rows if (row.get("settings") or {}).get("shuffle", False)]
        if due:
            selected = max(due, key=lambda row: now - self.last_priority[self.identity(row)])
            self.slot_type = "priority"
        elif shuffled and (not regular or self.regular_count >= 3):
            choices = [row for row in shuffled if self.identity(row) != self.current] or shuffled
            selected = self.rng.choice(choices)
            self.regular_count = 0
            self.slot_type = "shuffle"
        else:
            selected = regular[self.cursor % len(regular)]
            self.cursor = (self.cursor + 1) % len(regular)
            if self.identity(selected) == self.current and len(regular) > 1:
                selected = regular[self.cursor % len(regular)]
                self.cursor = (self.cursor + 1) % len(regular)
            self.regular_count += 1
            self.slot_type = "regular"
        self.current = self.identity(selected)
        self.started = now
        self.deadline = now + selected["duration_seconds"]
        self.last_priority[self.current] = now
        self.visits[self.current] = self.visits.get(self.current, 0) + 1
        self.generation += 1
        return selected

    def finish_cycle(self, cycle_seconds):
        """Round the slot up to a full asset loop, never interrupt a GIF mid-loop."""
        if cycle_seconds > 0:
            duration = self.deadline - self.started
            self.deadline = self.started + math.ceil(duration / cycle_seconds) * cycle_seconds
