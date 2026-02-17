from app.modules.base import ModuleBase, ModulePayload


class BTCModule(ModuleBase):
    key = "btc"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        price = cache.get("btc_eur")
        show_symbol = bool(settings.get("show_symbol", True))
        decimals = int(settings.get("decimals", 0))
        decimals = max(0, min(decimals, 2))

        if price is None:
            return ModulePayload(text="BTC ...")

        symbol = "€" if show_symbol else ""
        fmt = f"{{price:.{decimals}f}}"
        return ModulePayload(text=f"BTC {fmt.format(price=price)}{symbol}")
