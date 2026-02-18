from app.modules.base import ModuleBase, ModulePayload
from app.services.colors import parse_hex_color


class BitmapModule(ModuleBase):
    key = "bitmap"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        # Rendering happens in DisplayService because it can reuse the bitmap loader cache.
        color = parse_hex_color(settings.get("color"), (245, 245, 245))
        return ModulePayload(text="", default_color=color)
