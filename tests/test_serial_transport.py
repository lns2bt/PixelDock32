import logging
import threading
import unittest
from unittest.mock import patch

from app.config import Settings
from app.services.led_driver import FrameAckError, SerialLEDStrip
from tests.fake_uno import FakeUno


class SerialTransportTests(unittest.TestCase):
    def setUp(self):
        self.uno = FakeUno()
        settings = Settings(_env_file=None, led_serial_port="test-uno", led_serial_startup_delay=0)
        # Suppress only the automatic worker start. Individual tests can start it.
        with patch("app.services.led_driver.serial.Serial", return_value=self.uno), patch.object(threading.Thread, "start"):
            self.strip = SerialLEDStrip(settings, logging.getLogger("tests.serial"))
        self.addCleanup(self.cleanup_strip)

    def cleanup_strip(self):
        # Test harness cleanup; production lifecycle fix belongs to phase 2.
        self.strip._frame_sender_stop.set()
        self.strip._frame_sender_event.set()
        if self.strip._frame_sender_thread.is_alive():
            self.strip._frame_sender_thread.join(timeout=2)
        self.assertFalse(self.strip._frame_sender_thread.is_alive())
        self.strip._close_serial_locked()

    def test_capability_probe_enables_v2(self):
        self.assertTrue(self.strip._frame_ack_enabled)
        self.assertEqual(self.strip._protocol_version, 2)

    def test_packet_matches_known_wire_format(self):
        # Independent literal vector, not just two implementations agreeing.
        self.assertEqual(self.strip._build_packet(2, b"\x40"), bytes.fromhex("50 44 02 01 00 40 57"))
        self.assertEqual(len(self.strip._build_packet(5, b"\0" * 770)), 776)

    def test_successful_frame_is_confirmed(self):
        frame = bytes(range(256)) * 3
        self.strip._send_frame_with_retries(frame, 123, 1.5)
        self.assertEqual(self.uno.frame, frame)
        self.assertEqual(self.strip._stats["last_frame_ack_seq"], 123)
        self.assertEqual(self.strip.get_transport_metrics()["confirmations"]["confirmed_frames_total"], 1)

    def test_bad_ack_is_not_a_confirmation(self):
        for mode in ("missing", "wrong_sequence", "checksum"):
            with self.subTest(mode=mode):
                self.uno.ack_mode = mode
                with self.assertRaises(FrameAckError):
                    self.strip._write_frame_packet_locked(b"\0" * 768, 42)
                self.assertFalse(self.strip._stats["sender_waiting_for_ack"])
        self.assertEqual(self.strip.get_transport_metrics()["confirmations"]["confirmed_frames_total"], 0)

    def test_retry_records_only_one_success(self):
        original_read = self.uno.read
        failed = False

        def read(count):
            nonlocal failed
            if not failed:
                failed = True
                self.uno.responses.clear()
                return b""
            return original_read(count)

        with patch.object(self.uno, "read", side_effect=read), patch("app.services.led_driver.time.sleep"):
            self.strip._send_frame_with_retries(b"\0" * 768, 7, 0)
        self.assertEqual(self.strip._stats["frame_ack_timeouts"], 1)
        self.assertEqual(self.strip._stats["frame_ack_retry_successes"], 1)
        self.assertEqual(self.strip._frame_metrics.snapshot()["confirmed_frames_total"], 1)

    def test_v1_send_does_not_claim_confirmation(self):
        self.strip._frame_ack_enabled = False
        self.strip._send_frame_with_retries(b"\0" * 768, 5, None)
        self.assertEqual(self.strip._stats["frames_sent"], 1)
        self.assertEqual(self.strip._frame_metrics.snapshot()["confirmed_frames_total"], 0)

    def test_failed_retry_reconnects_and_resends_brightness_and_frame(self):
        replacement = FakeUno()
        self.uno.ack_mode = "missing"
        with patch("app.services.led_driver.serial.Serial", return_value=replacement), patch("app.services.led_driver.time.sleep"):
            self.strip._send_frame_with_retries(b"\x17" * 768, 9, 0)
        self.assertTrue(self.uno.closed)
        self.assertEqual(replacement.frame, b"\x17" * 768)
        self.assertIn(2, [data[2] for data in replacement.writes])
        self.assertEqual(self.strip._stats["reconnect_successes"], 1)
        self.assertFalse(self.strip.needs_frame_resync())
        self.assertEqual(self.strip._frame_metrics.snapshot()["confirmed_frames_total"], 1)

    def test_latest_frame_replaces_pending_and_is_copied(self):
        self.strip.setPixelColor(0, (1, 2, 3))
        self.strip.show()
        first = self.strip._pending_frame
        self.strip.setPixelColor(0, (4, 5, 6))
        self.strip.show()
        self.assertEqual(first[:3], b"\x01\x02\x03")
        self.assertEqual(self.strip._pending_frame[:3], b"\x04\x05\x06")
        self.assertEqual(self.strip._stats["frames_replaced_before_send"], 1)

    def test_sequence_wrap(self):
        self.strip._next_frame_seq = 65535
        self.assertEqual(self.strip._next_frame_sequence(), 65535)
        self.assertEqual(self.strip._next_frame_sequence(), 0)

    def test_metrics_never_touch_serial_lock_or_device(self):
        with self.strip._lock, patch.object(self.uno, "write", side_effect=AssertionError("serial I/O")), patch.object(self.uno, "read", side_effect=AssertionError("serial I/O")):
            self.assertFalse(self.strip.get_transport_metrics()["sender_thread_alive"])

    def test_ping_nonce(self):
        result = self.strip.ping(12345)
        self.assertTrue(result["ok"])
        self.assertEqual(result["response_nonce"], 12345)

    def test_indexed_colors_clear_previous_pixels(self):
        self.strip.set_indexed_colors({0: (1, 2, 3), 255: (4, 5, 6)})
        self.strip.set_indexed_colors({1: (7, 8, 9)})
        self.assertEqual(self.strip._buffer[:6], b"\0\0\0\x07\x08\x09")
        self.assertEqual(self.strip._buffer[-3:], b"\0\0\0")

    def test_sender_thread_delivers_and_harness_stops_it(self):
        delivered = threading.Event()
        original_send = self.strip._send_frame_with_retries

        def send(*args):
            original_send(*args)
            delivered.set()

        with patch.object(self.strip, "_send_frame_with_retries", side_effect=send):
            self.strip._frame_sender_thread.start()
            self.strip.show()
            self.assertTrue(delivered.wait(timeout=2))
        self.assertEqual(self.strip._stats["frames_sent"], 1)
