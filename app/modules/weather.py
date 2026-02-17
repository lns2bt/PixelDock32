from app.modules.base import ModuleBase, ModulePayload
from app.services.rendering import render_text_with_colors


def temperature_to_rgb(temp_c: float) -> tuple[int, int, int]:
    clamped = max(-15.0, min(35.0, temp_c))
    ratio = (clamped + 15.0) / 50.0
    red = int(40 + ratio * 215)
    blue = int(255 - ratio * 215)
    green = int(70 + (1 - abs(ratio - 0.5) * 2) * 70)
    return red, green, blue


class WeatherModule(ModuleBase):
    key = "weather"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        temp = cache.get("weather_temp")

        if temp is None:
            frame, colors = render_text_with_colors("...C", char_colors=[(120, 120, 120)] * 4)
            return ModulePayload(text="...C", frame=frame, color_frame=colors)

        value = float(temp)
        text = f"{value:.1f}C"
        color = temperature_to_rgb(value)
        frame, colors = render_text_with_colors(text, char_colors=[color] * len(text))
        return ModulePayload(text=text, frame=frame, color_frame=colors)
