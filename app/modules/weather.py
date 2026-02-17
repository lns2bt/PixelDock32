from app.modules.base import ModuleBase, ModulePayload


class WeatherModule(ModuleBase):
    key = "weather"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        temp = cache.get("weather_temp")
        unit = str(settings.get("unit", "C")).upper()

        if temp is None:
            return ModulePayload(text="IBK ...")

        if unit == "F":
            display_temp = (temp * 9 / 5) + 32
            suffix = "F"
        else:
            display_temp = temp
            suffix = "C"

        return ModulePayload(text=f"IBK {display_temp:.1f}{suffix}")
