from dataclasses import dataclass

from app.config import Settings

try:
    from rpi_ws281x import Color, PixelStrip
except ImportError:  # local dev fallback
    Color = None
    PixelStrip = None


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


class LEDDriver:
    def __init__(self, settings: Settings):
        self.settings = settings
        if PixelStrip is None:
            self.strip = MockStrip(settings.led_count)
            self._color = lambda r, g, b: (r, g, b)
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
        self.strip.begin()

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
