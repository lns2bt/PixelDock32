from app.modules.base import ModuleBase, ModulePayload
from app.services.colors import clamp, lerp_color, parse_hex_color


def temperature_to_rgb(temp_c: float, cold: tuple[int, int, int], warm: tuple[int, int, int]) -> tuple[int, int, int]:
    clamped = max(-15.0, min(35.0, temp_c))
    ratio = (clamped + 15.0) / 50.0
    return lerp_color(cold, warm, ratio)


class WeatherModule(ModuleBase):
    key = "weather"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        temp = cache.get("weather_temp")
        font_size = settings.get("font_size", "normal")
        x_offset = clamp(int(settings.get("x_offset", 0)), -16, 16)
        y_offset = clamp(int(settings.get("y_offset", 0)), -4, 4)

        cold_color = parse_hex_color(settings.get("color_cold"), (50, 120, 255))
        warm_color = parse_hex_color(settings.get("color_warm"), (255, 100, 70))
        fallback_color = parse_hex_color(settings.get("color_fallback"), (120, 120, 120))

        if temp is None:
            return ModulePayload(
                text="...C",
                font_size=font_size,
                x_offset=x_offset,
                y_offset=y_offset,
                default_color=fallback_color,
            )

        value = float(temp)
        text = f"{value:.1f}C"
        color = temperature_to_rgb(value, cold_color, warm_color)
        return ModulePayload(
            text=text,
            font_size=font_size,
            x_offset=x_offset,
            y_offset=y_offset,
            default_color=color,
        )
