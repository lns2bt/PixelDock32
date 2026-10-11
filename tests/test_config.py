import unittest

from pydantic import ValidationError

from app.config import Settings


class ConfigTests(unittest.TestCase):
    def test_default_fps_and_explicit_mock(self):
        self.assertEqual(Settings(_env_file=None).render_fps, 30)
        self.assertEqual(Settings(_env_file=None, led_transport="mock").led_transport, "mock")

    def test_uno_geometry_mismatch_is_rejected(self):
        for kwargs in ({"led_count": 64}, {"panel_columns": 16}, {"chain_panels": 2}):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None, led_transport="serial", **kwargs)

    def test_timeouts_are_positive_and_bounded(self):
        for kwargs in ({"led_serial_timeout": 0}, {"led_serial_write_timeout": -1}, {"led_serial_ack_timeout": 10}, {"render_fps": 0}):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None, **kwargs)
