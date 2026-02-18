from app.modules.base import ModuleBase, ModulePayload
from app.services.colors import clamp, parse_hex_color


class BTCModule(ModuleBase):
    key = "btc"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        price = cache.get("btc_eur")
        trend = cache.get("btc_trend", "flat")
        block_height = cache.get("btc_block_height")

        font_size = settings.get("font_size", "normal")
        x_offset = clamp(int(settings.get("x_offset", 0)), -16, 16)
        y_offset = clamp(int(settings.get("y_offset", 0)), -4, 4)
        char_spacing = clamp(int(settings.get("char_spacing", 1)), 0, 4)

        show_block_height = bool(settings.get("show_block_height", False))
        screen_seconds = clamp(int(settings.get("screen_seconds", 4)), 1, 60)

        base_b_color = parse_hex_color(settings.get("color_b"), (255, 140, 0))
        up_color = parse_hex_color(settings.get("color_up"), (0, 200, 80))
        down_color = parse_hex_color(settings.get("color_down"), (230, 60, 60))
        flat_color = parse_hex_color(settings.get("color_flat"), (220, 220, 80))
        fallback_color = parse_hex_color(settings.get("color_fallback"), (120, 120, 120))

        show_block_screen = show_block_height and block_height is not None
        if show_block_screen:
            now = cache.get("now")
            if not isinstance(now, (int, float)):
                import time

                now = time.time()
            screen_slot = int(now / screen_seconds) % 2
            if screen_slot == 1:
                block_text = f"H{int(block_height)}"
                return ModulePayload(
                    text=block_text,
                    font_size=font_size,
                    x_offset=x_offset,
                    y_offset=y_offset,
                    default_color=flat_color,
                    char_colors=[base_b_color] + [flat_color] * max(0, len(block_text) - 1),
                    char_spacing=char_spacing,
                )

        if price is None:
            return ModulePayload(
                text="B...k",
                font_size=font_size,
                x_offset=x_offset,
                y_offset=y_offset,
                default_color=fallback_color,
                char_colors=[base_b_color] + [fallback_color] * 4,
                char_spacing=char_spacing,
            )

        value_k = float(price) / 1000.0
        text = f"B{value_k:.1f}k"

        if trend == "up":
            price_color = up_color
        elif trend == "down":
            price_color = down_color
        else:
            price_color = flat_color

        return ModulePayload(
            text=text,
            font_size=font_size,
            x_offset=x_offset,
            y_offset=y_offset,
            default_color=price_color,
            char_colors=[base_b_color] + [price_color] * max(0, len(text) - 1),
            char_spacing=char_spacing,
        )
