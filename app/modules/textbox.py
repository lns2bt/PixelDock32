import time

from app.modules.base import ModuleBase, ModulePayload
from app.services.colors import clamp, parse_hex_color


class TextBoxModule(ModuleBase):
    key = "textbox"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        raw_lines = str(settings.get("lines", "HELLO\nPIXEL")).splitlines()
        lines = [line.strip() for line in raw_lines if line.strip()]
        if not lines:
            lines = ["..."]

        line_seconds = max(1, int(settings.get("line_seconds", 2)))
        idx = int(time.time() / line_seconds) % len(lines)
        text = lines[idx]

        font_size = settings.get("font_size", "small")
        color = parse_hex_color(settings.get("color"), (245, 245, 245))
        x_offset = clamp(int(settings.get("x_offset", 0)), -16, 16)
        y_offset = clamp(int(settings.get("y_offset", 0)), -4, 4)

        return ModulePayload(
            text=text,
            font_size=font_size,
            x_offset=x_offset,
            y_offset=y_offset,
            default_color=color,
        )
