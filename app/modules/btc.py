from app.modules.base import ModuleBase, ModulePayload


class BTCModule(ModuleBase):
    key = "btc"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        price = cache.get("btc_eur")

        if price is None:
            return ModulePayload(text="...k")

        value_k = float(price) / 1000.0
        return ModulePayload(text=f"{value_k:.1f}k")
