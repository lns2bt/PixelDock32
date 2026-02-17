from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.modules.base import ModuleBase, ModulePayload


class ClockModule(ModuleBase):
    key = "clock"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        tz = settings.get("timezone", get_settings().tz)
        now = datetime.now(ZoneInfo(tz))
        return ModulePayload(text=now.strftime("%H:%M:%S"))
