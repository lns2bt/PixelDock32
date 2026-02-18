import time

from app.modules.base import ModuleBase, ModulePayload
from app.services.colors import clamp, parse_hex_color


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class TextBoxModule(ModuleBase):
    key = "textbox"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        raw_lines = str(settings.get("lines", "HELLO\nPIXEL")).splitlines()
        lines = [line.strip() for line in raw_lines if line.strip()]
        if not lines:
            lines = ["..."]

        line_seconds = max(1, _safe_int(settings.get("line_seconds", 2), 2))
        idx = int(time.time() / line_seconds) % len(lines)
        text = lines[idx]

        font_size = settings.get("font_size", "small")
        color = parse_hex_color(settings.get("color"), (245, 245, 245))
        x_offset = clamp(_safe_int(settings.get("x_offset", 0), 0), -16, 16)
        y_offset = clamp(_safe_int(settings.get("y_offset", 0), 0), -4, 4)

        text_mode = settings.get("text_mode", "static")
        if text_mode not in {"static", "scroll"}:
            text_mode = "static"

        if text_mode == "scroll":
            speed = max(1, _safe_int(settings.get("scroll_speed", 35), 35))
            char_step = 4 if font_size == "small" else 6
            text_width = max(len(text) * char_step - 1, 1)
            cycle = text_width + 32
            offset = 32 - (int(time.time() * speed / 10) % cycle)
            x_offset = clamp(offset, -text_width, 32)

        return ModulePayload(
            text=text,
            font_size=font_size,
            x_offset=x_offset,
            y_offset=y_offset,
            default_color=color,
        )
