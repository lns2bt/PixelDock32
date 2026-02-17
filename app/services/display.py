import asyncio
import time
from collections.abc import Callable

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import ModuleConfig
from app.modules.base import ModulePayload
from app.modules.btc import BTCModule
from app.modules.clock import ClockModule
from app.modules.weather import WeatherModule
from app.services.led_driver import LEDDriver
from app.services.led_mapper import LEDMapper
from app.services.rendering import blank_color_frame, render_text_frame

MODULE_REGISTRY = {
    "clock": ClockModule(),
    "btc": BTCModule(),
    "weather": WeatherModule(),
}

DEBUG_COLORS = {
    "pixel_walk": (255, 210, 0),
    "panel_walk": (0, 180, 255),
    "stripes": (180, 100, 255),
    "border": (80, 220, 220),
}


class DisplayService:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        led_driver: LEDDriver,
        mapper: LEDMapper,
        cache_provider: Callable[[], dict],
        fps: int,
    ):
        self.session_factory = session_factory
        self.led_driver = led_driver
        self.mapper = mapper
        self.cache_provider = cache_provider
        self.frame_delay = 1 / fps
        self.target_fps = fps
        self._running = False
        self._task: asyncio.Task | None = None
        self.manual_override: tuple[list[list[int]], float] | None = None
        self.debug_override: tuple[str, float, float] | None = None

        self.last_frame_ts: float | None = None
        self.frame_counter = 0
        self.started_at = time.time()
        self.last_source = "module"
        self.last_module_key: str | None = None
        self.last_frame: list[list[int]] = [[0 for _ in range(32)] for _ in range(8)]
        self.last_color_frame: list[list[tuple[int, int, int] | None]] = blank_color_frame(32, 8)

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    def set_manual_text(self, text: str, seconds: int):
        self.manual_override = (render_text_frame(text), time.time() + seconds)

    def set_manual_pixels(self, pixels: list[list[int]], seconds: int):
        self.manual_override = (pixels, time.time() + seconds)

    def set_brightness(self, value: int):
        self.led_driver.set_brightness(value)

    def set_debug_pattern(self, pattern: str, seconds: int, interval_ms: int = 250):
        self.debug_override = (pattern, time.time() + seconds, max(interval_ms / 1000.0, 0.05))

    def clear_debug_pattern(self):
        self.debug_override = None

    def get_preview_frame(self) -> list[list[int]]:
        return [row[:] for row in self.last_frame]

    def get_preview_colors(self) -> list[list[tuple[int, int, int] | None]]:
        return [row[:] for row in self.last_color_frame]

    def get_status(self) -> dict:
        uptime = max(time.time() - self.started_at, 1)
        return {
            "running": self._running,
            "target_fps": self.target_fps,
            "actual_fps": round(self.frame_counter / uptime, 2),
            "last_frame_ts": self.last_frame_ts,
            "last_source": self.last_source,
            "last_module": self.last_module_key,
            "debug_active": bool(self.debug_override),
            "debug_pattern": self.debug_override[0] if self.debug_override else None,
            "debug_until": self.debug_override[1] if self.debug_override else None,
            "manual_active": bool(self.manual_override),
            "manual_until": self.manual_override[1] if self.manual_override else None,
        }

    async def _loop(self):
        while self._running:
            frame, color_frame = await self._get_next_frame()
            index_to_color: dict[int, tuple[int, int, int]] = {}
            for y, row in enumerate(frame):
                for x, val in enumerate(row):
                    if not val:
                        continue
                    led_index = self.mapper.xy_to_index(x, y)
                    color = color_frame[y][x] if color_frame and color_frame[y][x] else (80, 80, 80)
                    index_to_color[led_index] = color

            self.led_driver.write_color_frame(index_to_color)
            self.last_frame = [row[:] for row in frame]
            self.last_color_frame = [row[:] for row in color_frame]
            self.last_frame_ts = time.time()
            self.frame_counter += 1
            await asyncio.sleep(self.frame_delay)

    async def _get_next_frame(self) -> tuple[list[list[int]], list[list[tuple[int, int, int] | None]]]:
        if self.debug_override:
            from app.services.patterns import PATTERN_FACTORIES

            pattern, until, interval = self.debug_override
            if time.time() <= until and pattern in PATTERN_FACTORIES:
                self.last_source = "debug"
                tick = int(time.time() / interval)
                frame = PATTERN_FACTORIES[pattern](tick)
                color = DEBUG_COLORS.get(pattern, (120, 120, 120))
                color_frame = blank_color_frame(32, 8)
                for y in range(8):
                    for x in range(32):
                        if frame[y][x]:
                            color_frame[y][x] = color
                return frame, color_frame
            self.debug_override = None

        if self.manual_override:
            pixels, until = self.manual_override
            if time.time() <= until:
                self.last_source = "manual"
                color_frame = blank_color_frame(32, 8)
                for y in range(8):
                    for x in range(32):
                        if pixels[y][x]:
                            color_frame[y][x] = (240, 240, 240)
                return pixels, color_frame
            self.manual_override = None

        async with self.session_factory() as db:
            rows = (
                await db.execute(
                    ModuleConfig.__table__.select()
                    .where(ModuleConfig.enabled.is_(True))
                    .order_by(ModuleConfig.sort_order.asc())
                )
            ).mappings().all()

        if not rows:
            self.last_source = "idle"
            return [[0 for _ in range(32)] for _ in range(8)], blank_color_frame(32, 8)

        durations = [row["duration_seconds"] for row in rows]
        total = max(sum(durations), 1)
        t = int(time.time()) % total
        idx = 0
        for duration in durations:
            if t < duration:
                break
            t -= duration
            idx += 1
        selected = rows[min(idx, len(rows) - 1)]

        module = MODULE_REGISTRY.get(selected["key"])
        if not module:
            self.last_source = "module"
            self.last_module_key = None
            return [[0 for _ in range(32)] for _ in range(8)], blank_color_frame(32, 8)

        self.last_source = "module"
        self.last_module_key = selected["key"]
        payload: ModulePayload = await module.render(selected["settings"] or {}, self.cache_provider())
        frame = payload.frame or render_text_frame(payload.text)
        color_frame = payload.color_frame or blank_color_frame(32, 8)
        return frame, color_frame
