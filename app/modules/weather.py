from app.modules.base import ModuleBase, ModulePayload


class WeatherModule(ModuleBase):
    key = "weather"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        temp = cache.get("weather_temp")
        if temp is None:
            return ModulePayload(text="IBK ...")
        return ModulePayload(text=f"IBK {temp:.1f}C")
