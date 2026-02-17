from app.modules.base import ModuleBase, ModulePayload
from app.services.rendering import render_text_with_colors


class BTCModule(ModuleBase):
    key = "btc"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        price = cache.get("btc_eur")
        trend = cache.get("btc_trend", "flat")

        if price is None:
            frame, colors = render_text_with_colors("B...K", char_colors=[(255, 140, 0)] + [(120, 120, 120)] * 4)
            return ModulePayload(text="B...k", frame=frame, color_frame=colors)

        value_k = float(price) / 1000.0
        text = f"B{value_k:.1f}k"

        if trend == "up":
            price_color = (0, 200, 80)
        elif trend == "down":
            price_color = (230, 60, 60)
        else:
            price_color = (220, 220, 80)

        char_colors = [(255, 140, 0)] + [price_color] * max(0, len(text) - 1)
        frame, colors = render_text_with_colors(text, char_colors=char_colors)
        return ModulePayload(text=text, frame=frame, color_frame=colors)
