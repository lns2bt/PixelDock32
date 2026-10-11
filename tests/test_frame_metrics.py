import unittest

from app.services.frame_metrics import FrameMetrics, distribution


class FrameMetricsTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.metrics = FrameMetrics(window_seconds=2, capacity=100, clock=lambda: self.now)

    def test_empty_has_no_invented_timings(self):
        self.assertIsNone(self.metrics.snapshot()["ack_interval"]["p95_ms"])
        self.assertEqual(self.metrics.snapshot()["confirmed_frames_total"], 0)

    def test_confirmations_and_intervals(self):
        for self.now in (0.5, 1.0, 1.5):
            self.metrics.record_confirmation(16, 2)
        result = self.metrics.snapshot()
        self.assertEqual(result["confirmed_frames_total"], 3)
        self.assertEqual(result["confirmed_fps_window"], 2)
        self.assertEqual(result["ack_interval"]["count"], 2)
        self.assertEqual(result["ack_interval"]["p95_ms"], 500)
        self.assertEqual(result["successful_attempt_roundtrip"]["p50_ms"], 16)

    def test_idle_ages_out_samples_but_preserves_total(self):
        self.now = 1
        self.metrics.record_confirmation(16, None)
        self.now = 4
        result = self.metrics.snapshot()
        self.assertEqual(result["confirmed_frames_total"], 1)
        self.assertEqual(result["confirmed_fps_window"], 0)
        self.assertEqual(result["last_confirmation_age_ms"], 3000)
        self.assertEqual(result["queue_wait"]["count"], 0)

    def test_capacity_does_not_report_false_fps(self):
        metrics = FrameMetrics(capacity=2, clock=lambda: self.now)
        for self.now in (1, 2, 3):
            metrics.record_confirmation(16, 0)
        result = metrics.snapshot()
        self.assertTrue(result["window_truncated"])
        self.assertIsNone(result["confirmed_fps_window"])
        self.assertEqual(result["confirmed_frames_in_window"], 2)

    def test_snapshot_is_detached(self):
        result = self.metrics.snapshot()
        result["confirmed_frames_total"] = 999
        self.assertEqual(self.metrics.snapshot()["confirmed_frames_total"], 0)

    def test_nearest_rank_percentiles(self):
        result = distribution(list(range(1, 101)))
        self.assertEqual((result["p50_ms"], result["p95_ms"], result["p99_ms"]), (50, 95, 99))

    def test_regular_30_fps_window(self):
        for frame in range(1, 901):
            self.now = frame / 30
            self.metrics.record_confirmation(16, 0)
        result = self.metrics.snapshot()
        self.assertEqual(result["confirmed_fps_window"], 30)
        self.assertEqual(result["ack_interval"]["p99_ms"], 33.333)
        self.assertFalse(result["window_truncated"])

    def test_invalid_limits(self):
        for kwargs in ({"capacity": 1}, {"window_seconds": 0}):
            with self.assertRaises(ValueError):
                FrameMetrics(**kwargs)
