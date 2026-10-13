import time

from app.modules.base import ModuleBase, ModulePayload
from app.services.colors import clamp, parse_hex_color
from app.services.rendering import measure_text_width


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class TextBoxModule(ModuleBase):
    key = "textbox"

    @staticmethod
    def scroll_cycle(settings):
        lines = [line.strip() for line in str(settings.get("lines", "HELLO\nPIXEL")).splitlines() if line.strip()] or ["..."]
        speed = max(5, _safe_int(settings.get("scroll_speed", 35), 35))
        widths = [measure_text_width(line, font_size=settings.get("font_size", "small"), char_spacing=_safe_int(settings.get("char_spacing", 1), 1)) + 32 for line in lines]
        return lines, widths, speed

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        raw_lines = str(settings.get("lines", "HELLO\nPIXEL")).splitlines()
        lines = [line.strip() for line in raw_lines if line.strip()]
        if not lines:
            lines = ["..."]

        line_seconds = max(1, _safe_int(settings.get("line_seconds", 2), 2))
        elapsed = settings.get("_elapsed", time.monotonic())
        idx = int(elapsed / line_seconds) % len(lines)
        text = lines[idx]

        font_size = settings.get("font_size", "small")
        color = parse_hex_color(settings.get("color"), (245, 245, 245))
        x_offset = clamp(_safe_int(settings.get("x_offset", 0), 0), -16, 16)
        y_offset = clamp(_safe_int(settings.get("y_offset", 0), 0), -4, 4)
        char_spacing = clamp(_safe_int(settings.get("char_spacing", 1), 1), 0, 4)

        text_mode = settings.get("text_mode", "static")
        if text_mode not in {"static", "scroll"}:
            text_mode = "static"

        if text_mode == "scroll":
            lines, widths, speed = self.scroll_cycle(settings)
            position = (elapsed * speed) % sum(widths)
            for line, width in zip(lines, widths):
                text = line
                if position < width:
                    break
                position -= width
            x_offset = 32 - int(position)

        return ModulePayload(
            text=text,
            font_size=font_size,
            x_offset=x_offset,
            y_offset=y_offset,
            default_color=color,
            char_spacing=char_spacing,
            scene_key=text if text_mode == "static" else None,
        )
