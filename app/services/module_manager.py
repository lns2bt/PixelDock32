from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModuleConfig

DEFAULT_MODULES = [
    {
        "key": "clock",
        "name": "Clock",
        "sort_order": 0,
        "duration_seconds": 8,
        "settings": {
            "timezone": "Europe/Vienna",
            "show_seconds": True,
            "font_size": "normal",
            "color": "#c8e6ff",
            "x_offset": 0,
            "y_offset": 0,
            "transition_direction": "down",
            "transition_ms": 350,
        },
    },
    {
        "key": "btc",
        "name": "BTC EUR",
        "sort_order": 1,
        "duration_seconds": 10,
        "settings": {
            "font_size": "normal",
            "x_offset": 0,
            "y_offset": 0,
            "color_b": "#ff8c00",
            "color_up": "#00c850",
            "color_down": "#e63c3c",
            "color_flat": "#dcdc50",
            "color_fallback": "#9ca3af",
            "transition_direction": "down",
            "transition_ms": 350,
        },
    },
    {
        "key": "weather",
        "name": "Weather Innsbruck",
        "sort_order": 2,
        "duration_seconds": 10,
        "settings": {
            "postcode": "6020",
            "font_size": "normal",
            "x_offset": 0,
            "y_offset": 0,
            "color_cold": "#3b82f6",
            "color_warm": "#f97316",
            "color_fallback": "#9ca3af",
            "transition_direction": "down",
            "transition_ms": 350,
        },
    },
    {
        "key": "textbox",
        "name": "Text Box",
        "sort_order": 3,
        "duration_seconds": 12,
        "settings": {
            "lines": "HELLO\nPIXELDOCK",
            "line_seconds": 2,
            "font_size": "small",
            "color": "#f4f4f5",
            "x_offset": 0,
            "y_offset": 0,
            "transition_direction": "down",
            "transition_ms": 450,
        },
    },
]


async def ensure_default_modules(db: AsyncSession):
    result = await db.execute(select(ModuleConfig))
    existing = result.scalars().all()
    existing_by_key = {row.key: row for row in existing}

    inserted = False
    for item in DEFAULT_MODULES:
        if item["key"] in existing_by_key:
            continue
        db.add(ModuleConfig(enabled=True, **item))
        inserted = True

    if inserted:
        await db.commit()


async def list_modules(db: AsyncSession) -> list[ModuleConfig]:
    result = await db.execute(select(ModuleConfig).order_by(ModuleConfig.sort_order.asc()))
    return list(result.scalars().all())
