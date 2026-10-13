from dataclasses import dataclass
from glob import glob
import logging
import struct
import threading
import time

from app.config import Settings
from app.services.frame_metrics import FrameMetrics

try:
    from rpi_ws281x import Color, PixelStrip
except ImportError:  # local dev fallback
    Color = None
    PixelStrip = None

try:
    import serial
    from serial import SerialException
    from serial import SerialTimeoutException
    from serial.tools import list_ports
except ImportError:  # optional dependency when serial backend is disabled
    serial = None
    list_ports = None

    class SerialException(Exception):
        pass

    class SerialTimeoutException(SerialException):
        pass


@dataclass
class RGB:
    r: int
    g: int
    b: int


class FrameAckError(SerialException):
    pass


class MockStrip:
    def __init__(self, count: int):
        self.count = count
        self.pixels = [(0, 0, 0)] * count
        self.brightness = 64

    def begin(self):
        return None

    def numPixels(self):
        return self.count

    def setBrightness(self, brightness: int):
        self.brightness = brightness

    def setPixelColor(self, index: int, color):
        self.pixels[index] = color

    def show(self):
        return None


class SerialLEDStrip:
    MAGIC = b"PD"
    CMD_FRAME = 0x01
    CMD_BRIGHTNESS = 0x02
    CMD_PING = 0x03
    CMD_PING_ACK = 0x83
    CMD_DEBUG_SNAPSHOT = 0x04
    CMD_FRAME_V2 = 0x05
    CMD_DEBUG_SNAPSHOT_ACK = 0x84
    CMD_FRAME_ACK = 0x85
    CMD_BRIGHTNESS_V3 = 0x06
    CMD_BRIGHTNESS_ACK = 0x86
    FRAME_ACK_PROTOCOL_VERSION = 2

    def __init__(self, settings: Settings, logger: logging.Logger):
        if serial is None:
            raise RuntimeError("pyserial is required for led_transport=serial")

        self.settings = settings
        self._logger = logger
        self._count = settings.led_count
        self._brightness = settings.led_brightness
        self._lock = threading.Lock()
        self._queue_lock = threading.Lock()
        self._buffer = bytearray(self._count * 3)
        self._serial = None
        self._requested_port = str(settings.led_serial_port or "").strip() or "auto"
        self._startup_delay = max(0.0, float(settings.led_serial_startup_delay))
        self._ack_timeout = max(float(getattr(settings, "led_serial_ack_timeout", settings.led_serial_timeout)), 0.005)
        self._debug_poll_cache_ttl_s = 0.75
        self._frame_ack_supported = False
        self._frame_ack_enabled = False
        self._protocol_version = None
        self._protocol_probe_error = None
        self._next_frame_seq = 0
        self._sequence_lock = threading.Lock()
        self._frame_metrics = FrameMetrics()
        self._last_activity_at = time.monotonic()
        self._next_reconnect_at = 0.0
        self._desired_frame: bytes | None = None
        self._pending_frame: bytes | None = None
        self._pending_frame_seq: int | None = None
        self._pending_frame_queued_at: float | None = None
        self._frame_sender_event = threading.Event()
        self._frame_sender_stop = threading.Event()
        self._frame_sender_thread = threading.Thread(
            target=self._frame_sender_loop,
            name="PixelDockSerialFrameSender",
            daemon=True,
        )

        self._stats = {
            "connected": False,
            "port": None,
            "requested_port": self._requested_port,
            "selected_port": None,
            "port_candidates": [],
            "baudrate": settings.led_serial_baudrate,
            "frame_payload_bytes": len(self._buffer),
            "frames_sent": 0,
            "brightness_updates": 0,
            "brightness_resyncs": 0,
            "frame_write_timeouts": 0,
            "frame_write_timeout_retry_successes": 0,
            "frame_write_retries": 0,
            "frame_resync_required": False,
            "frame_ack_supported": False,
            "frame_ack_enabled": False,
            "frame_acks_received": 0,
            "frame_ack_timeouts": 0,
            "frame_ack_errors": 0,
            "frame_ack_retry_successes": 0,
            "last_frame_ack_ms": None,
            "last_frame_roundtrip_ms": None,
            "last_frame_seq": None,
            "last_frame_ack_seq": None,
            "ack_timeout": self._ack_timeout,
            "protocol_version": None,
            "protocol_probe_error": None,
            "bytes_sent": 0,
            "last_frame_at": None,
            "last_frame_write_ms": None,
            "last_ping_at": None,
            "last_ping_ok": None,
            "last_ping_rtt_ms": None,
            "last_ping_error": None,
            "last_error": None,
            "last_error_at": None,
            "open_attempts": 0,
            "reconnect_attempts": 0,
            "reconnect_successes": 0,
            "last_reconnect_at": None,
            "last_reconnect_error": None,
            "startup_delay": self._startup_delay,
            "last_debug_poll_at": None,
            "last_debug_poll_ok": None,
            "last_debug_poll_rtt_ms": None,
            "last_debug_poll_error": None,
            "arduino_debug": None,
            "debug_poll_cache_hits": 0,
            "frames_enqueued": 0,
            "frames_replaced_before_send": 0,
            "sender_busy": False,
            "sender_waiting_for_ack": False,
            "sender_queue_pending": False,
            "sender_loop_errors": 0,
            "sender_last_error": None,
            "sender_last_error_at": None,
            "last_frame_queue_wait_ms": None,
        }
        try:
            self._open_serial(initial_open=True)
            self._probe_protocol_capabilities()
        except (SerialException, OSError) as exc:
            self._record_error(f"initial serial connection failed: {exc}")
            self._close_serial_locked()
            self._stats["frame_resync_required"] = True
            self._next_reconnect_at = time.monotonic() + self.settings.led_serial_reconnect_delay
            self._logger.warning("Serial LED device unavailable; will retry latest frame: %s", exc)
        self._frame_sender_thread.start()

    def close(self):
        """Stop retries, join the sender, then release the port. Idempotent."""
        self._frame_sender_stop.set()
        self._frame_sender_event.set()
        if self._frame_sender_thread.ident is not None:
            timeout = self._startup_delay + 3 * (self._ack_timeout + self.settings.led_serial_write_timeout) + 3
            self._frame_sender_thread.join(timeout=timeout)
            if self._frame_sender_thread.is_alive():
                raise RuntimeError("serial sender did not stop within shutdown deadline")
        with self._lock:
            self._close_serial_locked()

    def _pause(self, seconds: float):
        if self._frame_sender_stop.wait(seconds):
            raise SerialException("serial transport is closing")

    def _is_auto_port(self) -> bool:
        return self._requested_port.strip().lower() in {"", "auto", "detect"}

    @staticmethod
    def _dedupe_keep_order(values: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            out.append(value)
        return out

    def _candidate_serial_ports(self) -> list[str]:
        if not self._is_auto_port():
            return [self._requested_port]

        ranked: list[tuple[int, str]] = []
        if list_ports is not None:
            try:
                for port in list_ports.comports():
                    device = str(getattr(port, "device", "") or "")
                    if not device:
                        continue
                    if not (device.startswith("/dev/ttyACM") or device.startswith("/dev/ttyUSB")):
                        continue
                    desc = f"{getattr(port, 'description', '')} {getattr(port, 'manufacturer', '')}".lower()
                    score = 10
                    if device.startswith("/dev/ttyACM"):
                        score -= 5
                    if "arduino" in desc or "genuino" in desc:
                        score -= 4
                    if "ch340" in desc or "ch341" in desc:
                        score -= 3
                    if "usb serial" in desc or "cdc" in desc:
                        score -= 1
                    ranked.append((score, device))
            except Exception:
                # Fall back to glob below; debug endpoint can still show candidates from globs.
                ranked = []

        if not ranked:
            ranked.extend((0, path) for path in sorted(glob("/dev/ttyACM*")))
            ranked.extend((1, path) for path in sorted(glob("/dev/ttyUSB*")))

        ranked.sort(key=lambda item: (item[0], item[1]))
        return self._dedupe_keep_order([device for _, device in ranked])

    def _prepare_serial_port(self, ser) -> None:
        if self._startup_delay > 0:
            # Arduino UNO toggles DTR on open and resets; give firmware time to boot.
            self._pause(self._startup_delay)
        try:
            ser.reset_input_buffer()
        except Exception:
            pass
        try:
            ser.reset_output_buffer()
        except Exception:
            pass

    def _open_serial(self, *, initial_open: bool) -> None:
        candidates = self._candidate_serial_ports()
        self._stats["open_attempts"] += 1
        self._stats["port_candidates"] = candidates
        self._stats["connected"] = False
        self._stats["selected_port"] = None

        if not candidates:
            mode_hint = " (LED_SERIAL_PORT=auto)" if self._is_auto_port() else ""
            raise SerialException(f"no serial port candidates found{mode_hint}")

        errors: list[str] = []
        for port in candidates:
            ser = None
            try:
                ser = serial.Serial(
                    port,
                    self.settings.led_serial_baudrate,
                    timeout=self.settings.led_serial_timeout,
                    write_timeout=self.settings.led_serial_write_timeout,
                )
                self._prepare_serial_port(ser)
                self._serial = ser
                self._stats["connected"] = True
                self._stats["port"] = port
                self._stats["selected_port"] = port
                self._stats["last_reconnect_error"] = None
                if not initial_open:
                    self._stats["last_reconnect_at"] = time.time()
                return
            except (SerialException, OSError) as exc:
                if ser is not None:
                    ser.close()
                errors.append(f"{port}: {exc}")

        error_text = "; ".join(errors) if errors else "unknown open error"
        self._stats["last_reconnect_error"] = error_text
        raise SerialException(f"unable to open serial LED port ({error_text})")

    def _close_serial_locked(self) -> None:
        if self._serial is None:
            return
        try:
            self._serial.close()
        except Exception:
            pass
        finally:
            self._serial = None
            self._stats["connected"] = False

    def _record_error(self, message: str) -> None:
        self._stats["last_error"] = message
        self._stats["last_error_at"] = time.time()

    def _record_sender_error(self, message: str) -> None:
        self._stats["sender_last_error"] = message
        self._stats["sender_last_error_at"] = time.time()

    def _probe_protocol_capabilities(self) -> None:
        with self._lock:
            self._probe_protocol_capabilities_locked()

    def _probe_protocol_capabilities_locked(self) -> None:
        self._frame_ack_supported = False
        self._frame_ack_enabled = False
        self._protocol_version = None
        self._protocol_probe_error = None
        self._stats["frame_ack_supported"] = False
        self._stats["frame_ack_enabled"] = False
        self._stats["protocol_version"] = None
        self._stats["protocol_probe_error"] = None

        if self._serial is None:
            self._protocol_probe_error = "serial port not open"
            self._stats["protocol_probe_error"] = self._protocol_probe_error
            return

        try:
            try:
                self._serial.reset_input_buffer()
            except Exception:
                pass
            self._write_packet(self.CMD_DEBUG_SNAPSHOT)
            payload, error = self._read_exact_packet(self.CMD_DEBUG_SNAPSHOT_ACK, 33)
            if error or payload is None:
                raise SerialException(error or "debug snapshot probe failed")
            version = int(payload[0])
            self._protocol_version = version
            self._frame_ack_supported = version >= self.FRAME_ACK_PROTOCOL_VERSION
            self._frame_ack_enabled = self._frame_ack_supported
        except Exception as exc:
            self._protocol_probe_error = str(exc)
            self._frame_ack_supported = False
            self._frame_ack_enabled = False
            self._logger.warning("Serial protocol capability probe failed; refusing unacknowledged frames: %s", exc)

        self._stats["protocol_version"] = self._protocol_version
        self._stats["protocol_probe_error"] = self._protocol_probe_error
        self._stats["frame_ack_supported"] = self._frame_ack_supported
        self._stats["frame_ack_enabled"] = self._frame_ack_enabled
        if not self._frame_ack_enabled:
            raise SerialException(self._protocol_probe_error or "firmware v2 or newer with frame ACK required")

    def _reconnect_locked(self, context: str) -> bool:
        if self._frame_sender_stop.is_set() or time.monotonic() < self._next_reconnect_at:
            return False
        self._stats["reconnect_attempts"] += 1
        self._close_serial_locked()
        try:
            self._open_serial(initial_open=False)
            self._probe_protocol_capabilities_locked()
            self._write_brightness_locked()
            self._stats["brightness_resyncs"] += 1
            self._stats["reconnect_successes"] += 1
            self._stats["frame_resync_required"] = True
            self._logger.warning(
                "Serial link reconnected after %s on %s",
                context,
                self._stats.get("selected_port") or self._stats.get("port"),
            )
            return True
        except (SerialException, OSError) as exc:
            self._close_serial_locked()
            self._next_reconnect_at = time.monotonic() + self.settings.led_serial_reconnect_delay
            message = f"serial reconnect failed after {context}: {exc}"
            self._stats["last_reconnect_error"] = message
            self._record_error(message)
            self._logger.warning("Serial reconnect failed after %s: %s", context, exc)
            return False

    @staticmethod
    def _checksum(data: bytes | bytearray) -> int:
        value = 0
        for byte in data:
            value ^= byte
        return value

    def _build_packet(self, command: int, payload: bytes | bytearray = b"") -> bytes:
        payload_len = len(payload)
        if payload_len > 0xFFFF:
            raise ValueError("payload too large")
        header = struct.pack("<2sBH", self.MAGIC, command, payload_len)
        body = header + payload
        return body + bytes([self._checksum(body)])

    def _write_packet(self, command: int, payload: bytes | bytearray = b""):
        if self._frame_sender_stop.is_set():
            raise SerialException("serial transport is closing")
        if self._serial is None:
            raise SerialException("serial port not open")
        packet = self._build_packet(command, payload)
        start = time.perf_counter()
        written = self._serial.write(packet)
        if written != len(packet):
            raise SerialTimeoutException(f"short serial write ({written}/{len(packet)} bytes)")
        elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
        self._stats["bytes_sent"] += len(packet)
        self._last_activity_at = time.monotonic()
        return elapsed_ms

    def begin(self):
        try:
            self.setBrightness(self._brightness)
        except (SerialException, OSError) as exc:
            self._record_error(f"initial brightness deferred: {exc}")
        self.show()

    def numPixels(self):
        return self._count

    def setBrightness(self, brightness: int):
        with self._lock:
            self._brightness = max(0, min(255, int(brightness)))
            self._stats["frame_resync_required"] = True
            try:
                self._write_brightness_locked()
            except (SerialException, OSError) as exc:
                message = f"serial brightness write failed: {exc}"
                self._record_error(message)
                self._logger.warning("Serial brightness write failed: %s", exc)
                if not self._reconnect_locked("brightness write"):
                    raise
                self._write_brightness_locked()
            self._stats["brightness_updates"] += 1

    def _write_brightness_locked(self):
        payload = bytes([self._brightness])
        if self._protocol_version is not None and self._protocol_version >= 3:
            self._write_packet(self.CMD_BRIGHTNESS_V3, payload)
            response, error = self._read_exact_packet(self.CMD_BRIGHTNESS_ACK, 1, timeout=self._ack_timeout)
            if error or response != payload:
                raise SerialException(error or "brightness ACK mismatch")
        else:
            # Old firmware calls show() without ACK. Drain TX, then allow its
            # interrupt-disabled LED output to finish before issuing any command.
            self._write_packet(self.CMD_BRIGHTNESS, payload)
            deadline = time.monotonic() + self.settings.led_serial_write_timeout
            while self._serial.out_waiting:
                if time.monotonic() >= deadline:
                    raise SerialTimeoutException("brightness TX drain timeout")
                self._pause(0.001)
            self._pause(self._count * 24 / 800000 + 0.02)

    def setPixelColor(self, index: int, color):
        if not (0 <= index < self._count):
            return

        if isinstance(color, tuple):
            r, g, b = color
        else:
            color = int(color)
            r = (color >> 16) & 0xFF
            g = (color >> 8) & 0xFF
            b = color & 0xFF

        offset = index * 3
        self._buffer[offset] = r
        self._buffer[offset + 1] = g
        self._buffer[offset + 2] = b

    def set_indexed_colors(self, index_to_color: dict[int, tuple[int, int, int]]):
        # Fast path for Pi->UNO serial transport: clear once, then write only lit pixels.
        self._buffer[:] = b"\x00" * len(self._buffer)
        for index, rgb in index_to_color.items():
            if not (0 <= index < self._count):
                continue
            offset = index * 3
            self._buffer[offset] = int(rgb[0]) & 0xFF
            self._buffer[offset + 1] = int(rgb[1]) & 0xFF
            self._buffer[offset + 2] = int(rgb[2]) & 0xFF

    def _next_frame_sequence(self) -> int:
        with self._sequence_lock:
            sequence = self._next_frame_seq & 0xFFFF
            self._next_frame_seq = (sequence + 1) & 0xFFFF
            return sequence

    def _enqueue_frame(self, frame_bytes: bytes, sequence: int) -> None:
        with self._queue_lock:
            self._desired_frame = frame_bytes
            if self._pending_frame is not None:
                self._stats["frames_replaced_before_send"] += 1
            self._pending_frame = frame_bytes
            self._pending_frame_seq = sequence
            self._pending_frame_queued_at = time.monotonic()
            self._stats["frames_enqueued"] += 1
            self._stats["sender_queue_pending"] = True
        self._frame_sender_event.set()

    def _queue_desired_frame_for_resync(self):
        sequence = self._next_frame_sequence()
        with self._queue_lock:
            if self._pending_frame is not None or self._desired_frame is None:
                return
            self._pending_frame = self._desired_frame
            self._pending_frame_seq = sequence
            self._pending_frame_queued_at = time.monotonic()
            self._stats["sender_queue_pending"] = True
            self._stats["frames_enqueued"] += 1
        self._frame_sender_event.set()

    def _reset_serial_buffers_locked(self) -> None:
        if self._serial is None:
            return
        try:
            self._serial.reset_input_buffer()
        except Exception:
            pass
        try:
            self._serial.reset_output_buffer()
        except Exception:
            pass

    def _write_frame_packet_locked(self, frame_bytes: bytes, sequence: int) -> tuple[float, float | None, float, int | None]:
        if self._serial is None:
            raise SerialException("serial port not open")
        if not self._frame_ack_enabled:
            raise SerialException("firmware v2 or newer with frame ACK required")

        if self._frame_ack_enabled:
            try:
                self._serial.reset_input_buffer()
            except Exception:
                pass

        start = time.perf_counter()
        if self._frame_ack_enabled:
            payload = struct.pack("<H", sequence) + frame_bytes
            write_ms = self._write_packet(self.CMD_FRAME_V2, payload)
        else:
            write_ms = self._write_packet(self.CMD_FRAME, frame_bytes)

        ack_ms: float | None = None
        ack_seq: int | None = None
        if self._frame_ack_enabled:
            self._stats["sender_waiting_for_ack"] = True
            ack_start = time.perf_counter()
            try:
                payload, error = self._read_exact_packet(
                    self.CMD_FRAME_ACK,
                    2,
                    timeout=self._ack_timeout,
                )
            finally:
                self._stats["sender_waiting_for_ack"] = False

            if error or payload is None:
                if error and error.startswith("timeout/incomplete"):
                    self._stats["frame_ack_timeouts"] += 1
                else:
                    self._stats["frame_ack_errors"] += 1
                raise FrameAckError(error or "frame ack read failed")

            ack_seq = struct.unpack("<H", payload)[0]
            if ack_seq != sequence:
                self._stats["frame_ack_errors"] += 1
                raise FrameAckError(f"frame ack sequence mismatch ({ack_seq} != {sequence})")

            ack_ms = round((time.perf_counter() - ack_start) * 1000, 3)

        total_ms = round((time.perf_counter() - start) * 1000, 3)
        return write_ms, ack_ms, total_ms, ack_seq

    def _send_frame_with_retries(self, frame_bytes: bytes, sequence: int, queue_wait_ms: float | None) -> None:
        with self._lock:
            if self._serial is None and not self._reconnect_locked("frame send"):
                raise SerialException("serial device unavailable; reconnect delayed")
            try:
                write_ms, ack_ms, total_ms, ack_seq = self._write_frame_packet_locked(frame_bytes, sequence)
            except (SerialTimeoutException, FrameAckError) as exc:
                is_write_timeout = isinstance(exc, SerialTimeoutException)
                if is_write_timeout:
                    self._stats["frame_write_timeouts"] += 1
                    message = f"serial frame write timeout: {exc}"
                    self._logger.warning("Serial frame write timeout: %s", exc)
                else:
                    message = f"serial frame ack failed: {exc}"
                    self._logger.warning("Serial frame ACK failed: %s", exc)
                self._record_error(message)

                self._stats["frame_write_retries"] += 1
                try:
                    self._reset_serial_buffers_locked()
                    # Allow the UNO parser to recover from partial packet / delayed ACK before retry.
                    self._pause(max(float(self.settings.led_serial_timeout), self._ack_timeout, 0.05))
                    write_ms, ack_ms, total_ms, ack_seq = self._write_frame_packet_locked(frame_bytes, sequence)
                    if is_write_timeout:
                        self._stats["frame_write_timeout_retry_successes"] += 1
                    else:
                        self._stats["frame_ack_retry_successes"] += 1
                except (SerialException, OSError) as retry_exc:
                    retry_message = f"{message}; retry failed: {retry_exc}"
                    self._record_error(retry_message)
                    self._logger.warning("Serial frame retry failed after %s: %s", "write timeout" if is_write_timeout else "ACK error", retry_exc)
                    if not self._reconnect_locked("frame transport retry"):
                        raise
                    write_ms, ack_ms, total_ms, ack_seq = self._write_frame_packet_locked(frame_bytes, sequence)
            except (SerialException, OSError) as exc:
                message = f"serial frame write failed: {exc}"
                self._record_error(message)
                self._logger.warning("Serial frame write failed: %s", exc)
                if not self._reconnect_locked("frame write"):
                    raise
                write_ms, ack_ms, total_ms, ack_seq = self._write_frame_packet_locked(frame_bytes, sequence)

            self._stats["frames_sent"] += 1
            if ack_seq is not None:
                self._stats["frame_acks_received"] += 1
                self._frame_metrics.record_confirmation(total_ms, queue_wait_ms)
            self._stats["last_frame_at"] = time.time()
            self._stats["last_frame_write_ms"] = write_ms
            self._stats["last_frame_ack_ms"] = ack_ms
            self._stats["last_frame_roundtrip_ms"] = total_ms
            self._stats["last_frame_seq"] = sequence
            self._stats["last_frame_ack_seq"] = ack_seq
            self._stats["last_frame_queue_wait_ms"] = queue_wait_ms
            self._stats["frame_resync_required"] = False

    def _frame_sender_loop(self) -> None:
        while not self._frame_sender_stop.is_set():
            self._frame_sender_event.wait(timeout=0.1)
            if self._frame_sender_stop.is_set():
                return
            if not self._frame_sender_event.is_set():
                try:
                    self._check_idle_connection()
                except (SerialException, OSError) as exc:
                    self._record_error(f"idle recovery failed: {exc}")
                    self._stats["frame_resync_required"] = True
                    if self._desired_frame is not None:
                        self._queue_desired_frame_for_resync()
            while not self._frame_sender_stop.is_set():
                with self._queue_lock:
                    if self._pending_frame is None or self._pending_frame_seq is None:
                        self._stats["sender_queue_pending"] = False
                        self._frame_sender_event.clear()
                        break
                    frame_bytes = self._pending_frame
                    sequence = self._pending_frame_seq
                    queued_at = self._pending_frame_queued_at
                    self._pending_frame = None
                    self._pending_frame_seq = None
                    self._pending_frame_queued_at = None
                    self._stats["sender_queue_pending"] = False

                queue_wait_ms = None
                if queued_at is not None:
                    queue_wait_ms = round((time.monotonic() - queued_at) * 1000, 3)

                self._stats["sender_busy"] = True
                try:
                    self._send_frame_with_retries(frame_bytes, sequence, queue_wait_ms)
                except Exception as exc:
                    self._stats["frame_resync_required"] = True
                    # Preserve the failed static image unless a newer one is
                    # already waiting. Retry without requiring another render.
                    with self._queue_lock:
                        if self._pending_frame is None:
                            self._pending_frame = frame_bytes
                            self._pending_frame_seq = sequence
                            self._pending_frame_queued_at = time.monotonic()
                            self._stats["sender_queue_pending"] = True
                    self._frame_sender_event.set()
                    self._stats["sender_loop_errors"] += 1
                    message = f"serial frame sender error: {exc}"
                    self._record_sender_error(message)
                    self._record_error(message)
                    self._logger.warning("Serial frame sender iteration failed: %s", exc)
                    self._frame_sender_stop.wait(self.settings.led_serial_reconnect_delay)
                finally:
                    self._stats["sender_busy"] = False
                    self._stats["sender_waiting_for_ack"] = False

    def show(self):
        if self._frame_sender_stop.is_set():
            raise RuntimeError("serial transport is closed")
        frame_copy = bytes(self._buffer)
        sequence = self._next_frame_sequence()
        self._enqueue_frame(frame_copy, sequence)

    def _check_idle_connection(self):
        # A static image otherwise has no traffic and would never notice USB
        # removal or an AVR reset. Do not add heartbeats during active playback.
        if self._desired_frame is None or time.monotonic() - self._last_activity_at < 2:
            return
        result = self.poll_debug_snapshot()
        if not result["ok"]:
            with self._lock:
                self._close_serial_locked()
                self._stats["frame_resync_required"] = True
            self._queue_desired_frame_for_resync()
        elif result["snapshot"]["frame_packets"] == 0 or result["snapshot"]["brightness"] != self._brightness:
            # A reset can keep the USB port alive. Restore brightness and image.
            with self._lock:
                self._stats["frame_resync_required"] = True
                self._write_brightness_locked()
            self._queue_desired_frame_for_resync()

    def ping(self, nonce: int | None = None) -> dict:
        if nonce is None:
            nonce = int(time.time() * 1000) & 0xFFFFFFFF

        payload = struct.pack("<I", nonce)
        expected_len = 2 + 1 + 2 + 4 + 1
        response = b""
        reconnected = False
        start = time.perf_counter()
        for attempt in range(2):
            try:
                with self._lock:
                    if self._serial is None:
                        raise SerialException("serial port not open")
                    self._serial.reset_input_buffer()
                    self._write_packet(self.CMD_PING, payload)
                    response = self._serial.read(expected_len)
                break
            except (SerialException, OSError) as exc:
                if attempt == 0:
                    with self._lock:
                        message = f"serial ping failed: {exc}"
                        self._record_error(message)
                        self._logger.warning("Serial ping failed (attempt 1): %s", exc)
                        reconnected = self._reconnect_locked("ping")
                    if reconnected:
                        continue
                rtt_ms = round((time.perf_counter() - start) * 1000, 3)
                error = f"serial ping failed: {exc}"
                self._stats["last_ping_at"] = time.time()
                self._stats["last_ping_ok"] = False
                self._stats["last_ping_rtt_ms"] = rtt_ms
                self._stats["last_ping_error"] = error
                self._record_error(error)
                return {
                    "ok": False,
                    "nonce": nonce,
                    "response_nonce": None,
                    "roundtrip_ms": rtt_ms,
                    "error": error,
                    "raw_response_hex": "",
                    "reconnected": reconnected,
                }

        rtt_ms = round((time.perf_counter() - start) * 1000, 3)

        ok = False
        error = None
        response_nonce = None
        if len(response) != expected_len:
            error = f"timeout/incomplete response ({len(response)} bytes)"
        else:
            head = response[:5]
            recv_payload = response[5:-1]
            recv_checksum = response[-1]
            if response[0:2] != self.MAGIC:
                error = "invalid magic in response"
            elif response[2] != self.CMD_PING_ACK:
                error = f"unexpected cmd in response ({response[2]})"
            elif struct.unpack("<H", response[3:5])[0] != 4:
                error = "invalid payload length in response header"
            elif self._checksum(response[:-1]) != recv_checksum:
                error = "checksum mismatch in response"
            elif len(recv_payload) != 4:
                error = f"invalid payload len ({len(recv_payload)})"
            else:
                response_nonce = struct.unpack("<I", recv_payload)[0]
                ok = response_nonce == nonce
                if not ok:
                    error = f"nonce mismatch ({response_nonce} != {nonce})"

        self._stats["last_ping_at"] = time.time()
        self._stats["last_ping_ok"] = ok
        self._stats["last_ping_rtt_ms"] = rtt_ms
        self._stats["last_ping_error"] = error
        if error:
            self._record_error(error)

        return {
            "ok": ok,
            "nonce": nonce,
            "response_nonce": response_nonce,
            "roundtrip_ms": rtt_ms,
            "error": error,
            "raw_response_hex": response.hex(),
            "reconnected": reconnected,
        }

    def _read_exact_packet(
        self,
        expected_cmd: int,
        expected_payload_len: int,
        *,
        timeout: float | None = None,
    ) -> tuple[bytes | None, str | None]:
        if self._serial is None:
            return None, "serial port not open"
        expected_len = 2 + 1 + 2 + expected_payload_len + 1
        previous_timeout = None
        if timeout is not None:
            try:
                previous_timeout = self._serial.timeout
                self._serial.timeout = timeout
            except Exception:
                previous_timeout = None
        try:
            response = self._serial.read(expected_len)
        finally:
            if timeout is not None and previous_timeout is not None:
                try:
                    self._serial.timeout = previous_timeout
                except Exception:
                    pass
        if len(response) != expected_len:
            return None, f"timeout/incomplete response ({len(response)} bytes)"

        recv_payload = response[5:-1]
        recv_checksum = response[-1]
        if response[0:2] != self.MAGIC:
            return None, "invalid magic in response"
        if response[2] != expected_cmd:
            return None, f"unexpected cmd in response ({response[2]})"
        if struct.unpack("<H", response[3:5])[0] != expected_payload_len:
            return None, "invalid payload length in response header"
        if self._checksum(response[:-1]) != recv_checksum:
            return None, "checksum mismatch in response"
        if len(recv_payload) != expected_payload_len:
            return None, f"invalid payload len ({len(recv_payload)})"
        return recv_payload, None

    def poll_debug_snapshot(self) -> dict:
        payload_len = 33
        reconnected = False
        start = time.perf_counter()
        try:
            for attempt in range(2):
                try:
                    with self._lock:
                        if self._serial is None:
                            raise SerialException("serial port not open")
                        self._serial.reset_input_buffer()
                        self._write_packet(self.CMD_DEBUG_SNAPSHOT)
                        payload, error = self._read_exact_packet(self.CMD_DEBUG_SNAPSHOT_ACK, payload_len)
                    break
                except (SerialException, OSError) as exc:
                    if attempt == 0:
                        with self._lock:
                            message = f"serial debug poll failed: {exc}"
                            self._record_error(message)
                            self._logger.warning("Serial debug poll failed (attempt 1): %s", exc)
                            reconnected = self._reconnect_locked("debug poll")
                        if reconnected:
                            continue
                    raise
        except (SerialException, OSError) as exc:
            rtt_ms = round((time.perf_counter() - start) * 1000, 3)
            error = f"serial debug poll failed: {exc}"
            self._stats["last_debug_poll_at"] = time.time()
            self._stats["last_debug_poll_rtt_ms"] = rtt_ms
            self._stats["last_debug_poll_ok"] = False
            self._stats["last_debug_poll_error"] = error
            self._record_error(error)
            self._logger.warning("Serial debug poll failed: %s", exc)
            return {"ok": False, "error": error, "roundtrip_ms": rtt_ms, "reconnected": reconnected}

        rtt_ms = round((time.perf_counter() - start) * 1000, 3)

        self._stats["last_debug_poll_at"] = time.time()
        self._stats["last_debug_poll_rtt_ms"] = rtt_ms
        self._stats["last_debug_poll_ok"] = error is None
        self._stats["last_debug_poll_error"] = error

        if error:
            self._record_error(error)
            return {"ok": False, "error": error, "roundtrip_ms": rtt_ms, "reconnected": reconnected}

        (
            version,
            uptime_ms,
            packets_ok,
            frame_packets,
            brightness_packets,
            ping_packets,
            debug_packets,
            checksum_errors,
            invalid_packets,
            timeouts,
            last_cmd,
            current_brightness,
        ) = struct.unpack("<BIIIIIIHHHBB", payload)

        snapshot = {
            "protocol_version": version,
            "uptime_ms": uptime_ms,
            "packets_ok": packets_ok,
            "frame_packets": frame_packets,
            "brightness_packets": brightness_packets,
            "ping_packets": ping_packets,
            "debug_packets": debug_packets,
            "checksum_errors": checksum_errors,
            "invalid_packets": invalid_packets,
            "packet_timeouts": timeouts,
            "last_command": last_cmd,
            "brightness": current_brightness,
        }
        self._stats["arduino_debug"] = snapshot
        return {"ok": True, "roundtrip_ms": rtt_ms, "snapshot": snapshot, "reconnected": reconnected}

    def get_debug_snapshot(self, *, poll: bool = True) -> dict:
        last_poll = self._stats.get("last_debug_poll_at")
        if last_poll and (time.time() - float(last_poll)) < self._debug_poll_cache_ttl_s:
            self._stats["debug_poll_cache_hits"] += 1
        elif poll:
            try:
                self.poll_debug_snapshot()
            except Exception as exc:  # defensive: debug endpoint must stay usable
                self._stats["last_debug_poll_at"] = time.time()
                self._stats["last_debug_poll_ok"] = False
                self._stats["last_debug_poll_error"] = f"unexpected debug poll error: {exc}"
                self._record_error(f"unexpected debug poll error: {exc}")
                self._logger.exception("Unexpected serial debug poll error")
        return {
            **self._stats,
            "brightness": self._brightness,
            "timeout": self.settings.led_serial_timeout,
            "write_timeout": self.settings.led_serial_write_timeout,
            "ack_timeout": self._ack_timeout,
            "startup_delay": self.settings.led_serial_startup_delay,
            "sender_thread_alive": self._frame_sender_thread.is_alive(),
        }

    def needs_frame_resync(self) -> bool:
        return bool(self._stats.get("frame_resync_required"))

    def get_transport_metrics(self) -> dict:
        # Never poll the device or acquire the serial I/O lock from a web request.
        counters = (
            "frames_sent", "frames_enqueued", "frames_replaced_before_send",
            "frame_ack_timeouts", "frame_ack_errors", "frame_write_timeouts",
            "frame_write_retries", "reconnect_attempts", "reconnect_successes",
            "sender_loop_errors",
        )
        return {
            "connected": self._stats["connected"],
            "protocol_version": self._protocol_version,
            "brightness_sync": "ack" if (self._protocol_version or 0) >= 3 else "legacy_guard",
            "frame_ack_enabled": self._frame_ack_enabled,
            "sender_thread_alive": self._frame_sender_thread.is_alive(),
            "counters": {key: self._stats[key] for key in counters},
            "confirmations": self._frame_metrics.snapshot(),
        }


class LEDDriver:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._logger = logging.getLogger(__name__)
        self.strip = None
        self.transport = settings.led_transport
        self._color = lambda r, g, b: (r, g, b)

        transport = settings.led_transport
        if transport == "auto":
            transport = "serial"

        self.transport = transport

        if transport == "serial":
            self.strip = SerialLEDStrip(settings, self._logger)
            self.strip.begin()
            self._logger.info("Using serial LED transport on %s @ %s baud", settings.led_serial_port, settings.led_serial_baudrate)

        elif transport == "mock":
            self._activate_mock_strip("Explicit development transport")

        elif transport == "rpi":
            if PixelStrip is None:
                self._activate_mock_strip("rpi_ws281x is not installed (pip install rpi-ws281x==5.0.0)")
            else:
                self.strip = PixelStrip(
                    settings.led_count,
                    settings.led_pin,
                    settings.led_freq_hz,
                    settings.led_dma,
                    settings.led_invert,
                    settings.led_brightness,
                    settings.led_channel,
                )
                self._color = Color
                try:
                    self.strip.begin()
                except RuntimeError as exc:
                    self._logger.warning(
                        "LED hardware initialization failed (%s). Falling back to mock strip.",
                        exc,
                    )
                    self._activate_mock_strip("LED hardware initialization failed")

        if self.strip is None:
            self._activate_mock_strip(f"Unsupported led transport '{transport}'")

    def _activate_mock_strip(self, reason: str):
        self._logger.warning("Using mock LED strip: %s", reason)
        self.strip = MockStrip(self.settings.led_count)
        self.strip.setBrightness(self.settings.led_brightness)
        self.transport = "mock"
        self._color = lambda r, g, b: (r, g, b)
        self.strip.begin()

    def get_debug_snapshot(self, *, poll: bool = True) -> dict:
        base = {
            "transport": self.transport,
            "led_count": self.settings.led_count,
            "brightness": getattr(self.strip, "_brightness", getattr(self.strip, "brightness", self.settings.led_brightness)),
            "strip_class": self.strip.__class__.__name__,
        }
        if isinstance(self.strip, SerialLEDStrip):
            base["serial"] = self.strip.get_debug_snapshot(poll=poll)
        return base

    def serial_ping(self, nonce: int | None = None) -> dict:
        if not isinstance(self.strip, SerialLEDStrip):
            return {"ok": False, "error": f"serial transport inactive (current={self.transport})"}
        return self.strip.ping(nonce=nonce)

    def get_transport_metrics(self) -> dict:
        result = {"transport": self.transport, "led_count": self.settings.led_count}
        if isinstance(self.strip, SerialLEDStrip):
            result["serial"] = self.strip.get_transport_metrics()
        return result

    def should_force_frame_send(self) -> bool:
        return isinstance(self.strip, SerialLEDStrip) and self.strip.needs_frame_resync()

    def set_brightness(self, brightness: int):
        self.strip.setBrightness(brightness)
        if not isinstance(self.strip, SerialLEDStrip):
            self.strip.show()

    def close(self):
        if isinstance(self.strip, SerialLEDStrip):
            self.strip.close()

    def write_frame(self, indices_to_on: list[int], color: RGB | None = None):
        color = color or RGB(80, 80, 80)
        on_set = set(indices_to_on)
        for i in range(self.strip.numPixels()):
            if i in on_set:
                self.strip.setPixelColor(i, self._color(color.r, color.g, color.b))
            else:
                self.strip.setPixelColor(i, self._color(0, 0, 0))
        self.strip.show()

    def write_color_frame(self, index_to_color: dict[int, tuple[int, int, int]]):
        if isinstance(self.strip, SerialLEDStrip):
            self.strip.set_indexed_colors(index_to_color)
            self.strip.show()
            return
        for i in range(self.strip.numPixels()):
            rgb = index_to_color.get(i)
            if rgb is None:
                self.strip.setPixelColor(i, self._color(0, 0, 0))
            else:
                self.strip.setPixelColor(i, self._color(rgb[0], rgb[1], rgb[2]))
        self.strip.show()
