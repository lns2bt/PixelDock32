from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import get_settings
from app.modules.base import ModuleBase, ModulePayload


class ClockModule(ModuleBase):
    key = "clock"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        tz_name = settings.get("timezone", get_settings().tz)
        show_seconds = bool(settings.get("show_seconds", True))

        try:
            now = datetime.now(ZoneInfo(tz_name))
        except ZoneInfoNotFoundError:
            now = datetime.now(ZoneInfo(get_settings().tz))

        fmt = "%H:%M:%S" if show_seconds else "%H:%M"
        font_size = settings.get("font_size", "normal")
        return ModulePayload(text=now.strftime(fmt), font_size=font_size)
