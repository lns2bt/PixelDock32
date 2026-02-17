from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModuleConfig

DEFAULT_MODULES = [
    {
        "key": "clock",
        "name": "Clock",
        "sort_order": 0,
        "duration_seconds": 8,
        "settings": {"timezone": "Europe/Vienna", "show_seconds": True},
    },
    {
        "key": "btc",
        "name": "BTC EUR",
        "sort_order": 1,
        "duration_seconds": 10,
        "settings": {"show_symbol": True, "decimals": 0},
    },
    {
        "key": "weather",
        "name": "Weather Innsbruck",
        "sort_order": 2,
        "duration_seconds": 10,
        "settings": {"postcode": "6020", "unit": "C"},
    },
]


async def ensure_default_modules(db: AsyncSession):
    result = await db.execute(select(ModuleConfig))
    existing = result.scalars().all()
    if existing:
        return
    for item in DEFAULT_MODULES:
        db.add(ModuleConfig(enabled=True, **item))
    await db.commit()


async def list_modules(db: AsyncSession) -> list[ModuleConfig]:
    result = await db.execute(select(ModuleConfig).order_by(ModuleConfig.sort_order.asc()))
    return list(result.scalars().all())
