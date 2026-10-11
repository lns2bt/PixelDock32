import unittest

from app.services.frame_pacer import FramePacer


class FramePacerTests(unittest.TestCase):
    def test_work_time_and_wakeup_delay_do_not_accumulate_drift(self):
        pacer = FramePacer(30, 0)
        self.assertAlmostEqual(pacer.next_delay(0.010), 1 / 30 - 0.010)
        self.assertAlmostEqual(pacer.next_delay(1 / 30 + 0.005), 1 / 30 - 0.005)
        self.assertEqual(pacer.missed_deadlines, 0)

    def test_late_frames_skip_deadlines_instead_of_bursting(self):
        pacer = FramePacer(30, 0)
        delay = pacer.next_delay(0.110)
        self.assertAlmostEqual(delay, 4 / 30 - 0.110)
        self.assertEqual(pacer.missed_deadlines, 3)
        self.assertGreater(delay, 0)

    def test_invalid_fps(self):
        with self.assertRaises(ValueError):
            FramePacer(0, 0)
