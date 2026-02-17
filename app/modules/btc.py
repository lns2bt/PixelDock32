from app.modules.base import ModuleBase, ModulePayload


class BTCModule(ModuleBase):
    key = "btc"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        price = cache.get("btc_eur")
        if price is None:
            return ModulePayload(text="BTC ...")
        return ModulePayload(text=f"BTC {price:.0f}€")
