from dataclasses import dataclass
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
except ImportError:  # optional dependency when serial backend is disabled
    serial = None

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

    def __init__(self, settings: Settings, logger: logging.Logger):
        if serial is None:
            raise RuntimeError("pyserial is required for led_transport=serial")

        self.settings = settings
        self._logger = logger
        self._count = settings.led_count
        self._brightness = settings.led_brightness
        self._lock = threading.Lock()
        self._buffer = bytearray(self._count * 3)
        self._serial = serial.Serial(
            settings.led_serial_port,
            settings.led_serial_baudrate,
            timeout=settings.led_serial_timeout,
            write_timeout=settings.led_serial_write_timeout,
        )

        self._stats = {
            "connected": True,
            "port": settings.led_serial_port,
            "baudrate": settings.led_serial_baudrate,
            "frame_payload_bytes": len(self._buffer),
            "frames_sent": 0,
            "brightness_updates": 0,
            "bytes_sent": 0,
            "last_frame_at": None,
            "last_frame_write_ms": None,
            "last_ping_at": None,
            "last_ping_ok": None,
            "last_ping_rtt_ms": None,
            "last_error": None,
            "last_error_at": None,
        }

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
        packet = self._build_packet(command, payload)
        start = time.perf_counter()
        self._serial.write(packet)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
        self._stats["bytes_sent"] += len(packet)
        self._stats["last_frame_write_ms"] = elapsed_ms
        return elapsed_ms

    def begin(self):
        self.setBrightness(self._brightness)

    def numPixels(self):
        return self._count

    def setBrightness(self, brightness: int):
        self._brightness = max(0, min(255, int(brightness)))
        payload = bytes([self._brightness])
        with self._lock:
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

    def show(self):
        with self._lock:
            try:
                elapsed_ms = self._write_packet(self.CMD_FRAME, self._buffer)
            except (SerialException, OSError) as exc:
                self._stats["last_error"] = str(exc)
                self._stats["last_error_at"] = time.time()
                self._logger.warning("Serial frame write failed: %s", exc)
                raise
            self._stats["frames_sent"] += 1
            self._stats["last_frame_at"] = time.time()
            self._stats["last_frame_write_ms"] = elapsed_ms

    def ping(self, nonce: int | None = None) -> dict:
        if nonce is None:
            nonce = int(time.time() * 1000) & 0xFFFFFFFF

        payload = struct.pack("<I", nonce)
        with self._lock:
            start = time.perf_counter()
            self._write_packet(self.CMD_PING, payload)
            expected_len = 2 + 1 + 2 + 4 + 1
            response = self._serial.read(expected_len)
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
        if error:
            self._stats["last_error"] = error
            self._stats["last_error_at"] = time.time()

        return {
            "ok": ok,
            "nonce": nonce,
            "response_nonce": response_nonce,
            "roundtrip_ms": rtt_ms,
            "error": error,
            "raw_response_hex": response.hex(),
        }

    def get_debug_snapshot(self) -> dict:
        return {
            **self._stats,
            "brightness": self._brightness,
            "timeout": self.settings.led_serial_timeout,
            "write_timeout": self.settings.led_serial_write_timeout,
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
        for i in range(self.strip.numPixels()):
            rgb = index_to_color.get(i)
            if rgb is None:
                self.strip.setPixelColor(i, self._color(0, 0, 0))
            else:
                self.strip.setPixelColor(i, self._color(rgb[0], rgb[1], rgb[2]))
        self.strip.show()
