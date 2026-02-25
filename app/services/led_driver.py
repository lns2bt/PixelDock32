from dataclasses import dataclass
from glob import glob
import logging
import struct
import threading
import time

from app.config import Settings

try:
    from rpi_ws281x import Color, PixelStrip
except ImportError:  # local dev fallback
    Color = None
    PixelStrip = None

try:
    import serial
    from serial import SerialException
    from serial.tools import list_ports
except ImportError:  # optional dependency when serial backend is disabled
    serial = None
    list_ports = None

    class SerialException(Exception):
        pass


@dataclass
class RGB:
    r: int
    g: int
    b: int


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
    CMD_DEBUG_SNAPSHOT_ACK = 0x84

    def __init__(self, settings: Settings, logger: logging.Logger):
        if serial is None:
            raise RuntimeError("pyserial is required for led_transport=serial")

        self.settings = settings
        self._logger = logger
        self._count = settings.led_count
        self._brightness = settings.led_brightness
        self._lock = threading.Lock()
        self._buffer = bytearray(self._count * 3)
        self._serial = None
        self._requested_port = str(settings.led_serial_port or "").strip() or "auto"
        self._startup_delay = max(0.0, float(settings.led_serial_startup_delay))

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
        }
        self._open_serial(initial_open=True)

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
            time.sleep(self._startup_delay)
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

    def _reconnect_locked(self, context: str) -> bool:
        self._stats["reconnect_attempts"] += 1
        self._close_serial_locked()
        try:
            self._open_serial(initial_open=False)
            brightness_payload = bytes([self._brightness])
            self._write_packet(self.CMD_BRIGHTNESS, brightness_payload)
            self._stats["brightness_resyncs"] += 1
            self._stats["reconnect_successes"] += 1
            self._logger.warning(
                "Serial link reconnected after %s on %s",
                context,
                self._stats.get("selected_port") or self._stats.get("port"),
            )
            return True
        except (SerialException, OSError) as exc:
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
        if self._serial is None:
            raise SerialException("serial port not open")
        packet = self._build_packet(command, payload)
        start = time.perf_counter()
        self._serial.write(packet)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
        self._stats["bytes_sent"] += len(packet)
        return elapsed_ms

    def begin(self):
        self.setBrightness(self._brightness)

    def numPixels(self):
        return self._count

    def setBrightness(self, brightness: int):
        self._brightness = max(0, min(255, int(brightness)))
        payload = bytes([self._brightness])
        with self._lock:
            try:
                self._write_packet(self.CMD_BRIGHTNESS, payload)
            except (SerialException, OSError) as exc:
                message = f"serial brightness write failed: {exc}"
                self._record_error(message)
                self._logger.warning("Serial brightness write failed: %s", exc)
                if not self._reconnect_locked("brightness write"):
                    raise
                self._write_packet(self.CMD_BRIGHTNESS, payload)
            self._stats["brightness_updates"] += 1

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

    def show(self):
        with self._lock:
            try:
                elapsed_ms = self._write_packet(self.CMD_FRAME, self._buffer)
            except (SerialException, OSError) as exc:
                message = f"serial frame write failed: {exc}"
                self._record_error(message)
                self._logger.warning("Serial frame write failed: %s", exc)
                if not self._reconnect_locked("frame write"):
                    raise
                elapsed_ms = self._write_packet(self.CMD_FRAME, self._buffer)
            self._stats["frames_sent"] += 1
            self._stats["last_frame_at"] = time.time()
            self._stats["last_frame_write_ms"] = elapsed_ms

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

    def _read_exact_packet(self, expected_cmd: int, expected_payload_len: int) -> tuple[bytes | None, str | None]:
        if self._serial is None:
            return None, "serial port not open"
        expected_len = 2 + 1 + 2 + expected_payload_len + 1
        response = self._serial.read(expected_len)
        if len(response) != expected_len:
            return None, f"timeout/incomplete response ({len(response)} bytes)"

        recv_payload = response[5:-1]
        recv_checksum = response[-1]
        if response[0:2] != self.MAGIC:
            return None, "invalid magic in response"
        if response[2] != expected_cmd:
            return None, f"unexpected cmd in response ({response[2]})"
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

    def get_debug_snapshot(self) -> dict:
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
            "startup_delay": self.settings.led_serial_startup_delay,
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
            transport = "rpi" if PixelStrip is not None else "serial"

        self.transport = transport

        if transport == "serial":
            try:
                self.strip = SerialLEDStrip(settings, self._logger)
                self.strip.begin()
            except (SerialException, RuntimeError, OSError) as exc:
                self._logger.warning("Serial LED init failed (%s). Falling back to mock strip.", exc)
                self._activate_mock_strip("Serial LED initialization failed")
            else:
                self._logger.info(
                    "Using serial LED transport on %s @ %s baud",
                    settings.led_serial_port,
                    settings.led_serial_baudrate,
                )

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
        self.transport = "mock"
        self._color = lambda r, g, b: (r, g, b)
        self.strip.begin()

    def get_debug_snapshot(self) -> dict:
        base = {
            "transport": self.transport,
            "led_count": self.settings.led_count,
            "brightness": getattr(self.strip, "brightness", self.settings.led_brightness),
            "strip_class": self.strip.__class__.__name__,
        }
        if isinstance(self.strip, SerialLEDStrip):
            base["serial"] = self.strip.get_debug_snapshot()
        return base

    def serial_ping(self, nonce: int | None = None) -> dict:
        if not isinstance(self.strip, SerialLEDStrip):
            return {"ok": False, "error": f"serial transport inactive (current={self.transport})"}
        return self.strip.ping(nonce=nonce)

    def set_brightness(self, brightness: int):
        self.strip.setBrightness(brightness)
        if not isinstance(self.strip, SerialLEDStrip):
            self.strip.show()

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
