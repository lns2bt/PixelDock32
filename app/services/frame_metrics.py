"""Bounded, passive host-side measurements of successful frame confirmations."""

from collections import deque
import math
import threading
import time


def distribution(values: list[float]) -> dict:
    """Nearest-rank percentiles; no invented zero values for empty samples."""
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "p50_ms": None, "p95_ms": None, "p99_ms": None, "max_ms": None}
    return {
        "count": len(ordered),
        **{
            f"p{percentile}_ms": round(ordered[math.ceil(len(ordered) * percentile / 100) - 1], 3)
            for percentile in (50, 95, 99)
        },
        "max_ms": round(ordered[-1], 3),
    }


class FrameMetrics:
    def __init__(self, window_seconds: float = 30.0, capacity: int = 2048, clock=time.monotonic):
        if window_seconds <= 0 or capacity < 2:
            raise ValueError("positive window and capacity >= 2 required")
        self._clock = clock
        self._started = clock()
        self._window = window_seconds
        self._samples = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._confirmed = 0
        self._last_ack = None

    def record_confirmation(self, roundtrip_ms: float, queue_wait_ms: float | None):
        with self._lock:
            now = self._clock()
            interval = None if self._last_ack is None else (now - self._last_ack) * 1000
            self._samples.append((now, interval, roundtrip_ms, queue_wait_ms))
            self._last_ack = now
            self._confirmed += 1

    def snapshot(self) -> dict:
        with self._lock:
            now = self._clock()
            samples = [sample for sample in self._samples if sample[0] > now - self._window]
            elapsed = min(max(now - self._started, 0.0), self._window)
            truncated = len(self._samples) == self._samples.maxlen and self._samples[0][0] > now - self._window
            return {
                "measurement": "host_received_frame_ack",
                "window_seconds": self._window,
                "window_elapsed_seconds": round(elapsed, 3),
                "window_truncated": truncated,
                "confirmed_frames_total": self._confirmed,
                "confirmed_frames_in_window": len(samples),
                "confirmed_fps_window": round(len(samples) / elapsed, 3) if elapsed > 0 and not truncated else None,
                "last_confirmation_age_ms": round((now - self._last_ack) * 1000, 3) if self._last_ack is not None else None,
                "ack_interval": distribution([s[1] for s in samples if s[1] is not None]),
                "successful_attempt_roundtrip": distribution([s[2] for s in samples]),
                "queue_wait": distribution([s[3] for s in samples if s[3] is not None]),
            }
