import time

from app.modules.base import ModuleBase, ModulePayload
from app.services.colors import clamp, lerp_color, parse_hex_color


def temperature_to_rgb(temp_c: float, cold: tuple[int, int, int], warm: tuple[int, int, int]) -> tuple[int, int, int]:
    clamped = max(-15.0, min(35.0, temp_c))
    ratio = (clamped + 15.0) / 50.0
    return lerp_color(cold, warm, ratio)


class WeatherModule(ModuleBase):
    key = "weather"

    @staticmethod
    def _format_temp(prefix: str, value: float) -> str:
        separator = "" if value < 0 else " "
        return f"{prefix}{separator}{value:.1f}C"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        outdoor_temp = cache.get("weather_outdoor_temp")
        indoor_temp = cache.get("weather_indoor_temp")
        indoor_humidity = cache.get("weather_indoor_humidity")

        font_size = settings.get("font_size", "normal")
        x_offset = clamp(int(settings.get("x_offset", 0)), -16, 16)
        y_offset = clamp(int(settings.get("y_offset", 0)), -4, 4)
        char_spacing = clamp(int(settings.get("char_spacing", 1)), 0, 4)
        screen_seconds = clamp(int(settings.get("screen_seconds", 4)), 1, 60)

        cold_color = parse_hex_color(settings.get("color_cold"), (50, 120, 255))
        warm_color = parse_hex_color(settings.get("color_warm"), (255, 100, 70))
        humidity_color = parse_hex_color(settings.get("color_humidity"), (110, 210, 255))
        fallback_color = parse_hex_color(settings.get("color_fallback"), (120, 120, 120))

        screens: list[tuple[str, tuple[int, int, int]]] = []

        if outdoor_temp is not None:
            outdoor_value = float(outdoor_temp)
            screens.append((self._format_temp("Out", outdoor_value), temperature_to_rgb(outdoor_value, cold_color, warm_color)))

        if indoor_temp is not None:
            indoor_value = float(indoor_temp)
            screens.append((self._format_temp("In", indoor_value), temperature_to_rgb(indoor_value, cold_color, warm_color)))

        if indoor_humidity is not None:
            screens.append((f"H{float(indoor_humidity):.0f}%", humidity_color))

        if not screens:
            return ModulePayload(
                text="W...",
                font_size=font_size,
                x_offset=x_offset,
                y_offset=y_offset,
                default_color=fallback_color,
                char_spacing=char_spacing,
            )

        now = cache.get("now")
        if not isinstance(now, (int, float)):
            now = time.time()
        screen_slot = int(now / screen_seconds) % len(screens)
        text, color = screens[screen_slot]

        return ModulePayload(
            text=text,
            font_size=font_size,
            x_offset=x_offset,
            y_offset=y_offset,
            default_color=color,
            char_spacing=char_spacing,
        )
