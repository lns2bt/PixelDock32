import asyncio
import time
from collections.abc import Callable

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import ModuleConfig
from app.modules.base import ModulePayload
from app.modules.btc import BTCModule
from app.modules.clock import ClockModule
from app.modules.weather import WeatherModule
from app.modules.textbox import TextBoxModule
from app.services.led_driver import LEDDriver
from app.services.led_mapper import LEDMapper
from app.services.colors import parse_hex_color
from app.services.rendering import blank_color_frame, render_text_with_colors

MODULE_REGISTRY = {
    "clock": ClockModule(),
    "btc": BTCModule(),
    "weather": WeatherModule(),
    "textbox": TextBoxModule(),
}

DEBUG_COLORS = {
    "pixel_walk": (255, 210, 0),
    "panel_walk": (0, 180, 255),
    "stripes": (180, 100, 255),
    "border": (80, 220, 220),
}


def _safe_int(value: object, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback

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
        self.manual_override: tuple[list[list[int]], list[list[tuple[int, int, int] | None]], float] | None = None
        self.debug_override: tuple[str, float, float] | None = None

        self.last_frame_ts: float | None = None
        self.frame_counter = 0
        self.started_at = time.time()
        self.last_source = "module"
        self.last_module_key: str | None = None
        self.last_frame: list[list[int]] = [[0 for _ in range(32)] for _ in range(8)]
        self.last_color_frame: list[list[tuple[int, int, int] | None]] = blank_color_frame(32, 8)
        self.transition_state: dict | None = None
        self.last_target_key: str | None = None
        self.last_target_frame: list[list[int]] = [[0 for _ in range(32)] for _ in range(8)]
        self.last_target_colors: list[list[tuple[int, int, int] | None]] = blank_color_frame(32, 8)

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    def set_manual_text(
        self,
        text: str,
        seconds: int,
        font_size: str = "normal",
        color: str = "#f0f0f0",
        x_offset: int = 0,
        y_offset: int = 0,
    ):
        parsed_color = parse_hex_color(color, (240, 240, 240))
        frame, color_frame = render_text_with_colors(
            text,
            font_size=font_size,
            base_color=parsed_color,
            x_offset=x_offset,
            y_offset=y_offset,
        )
        self.manual_override = (frame, color_frame, time.time() + seconds)

    def set_manual_pixels(self, pixels: list[list[int]], seconds: int):
        color_frame = blank_color_frame(32, 8)
        for y in range(8):
            for x in range(32):
                if pixels[y][x]:
                    color_frame[y][x] = (240, 240, 240)
        self.manual_override = (pixels, color_frame, time.time() + seconds)

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
            "manual_until": self.manual_override[2] if self.manual_override else None,
        }


    @staticmethod
    def _slide_vertical(
        from_frame: list[list[int]],
        from_colors: list[list[tuple[int, int, int] | None]],
        to_frame: list[list[int]],
        to_colors: list[list[tuple[int, int, int] | None]],
        progress: float,
        direction: str,
    ) -> tuple[list[list[int]], list[list[tuple[int, int, int] | None]]]:
        progress = max(0.0, min(1.0, progress))
        shift = int(round(progress * 8))
        out_frame = [[0 for _ in range(32)] for _ in range(8)]
        out_colors = blank_color_frame(32, 8)

        if direction == "down":
            old_shift = shift
            new_shift = shift - 8
        else:
            old_shift = -shift
            new_shift = 8 - shift

        for y in range(8):
            oy = y - old_shift
            ny = y - new_shift
            for x in range(32):
                if 0 <= oy < 8 and from_frame[oy][x]:
                    out_frame[y][x] = 1
                    out_colors[y][x] = from_colors[oy][x]
                if 0 <= ny < 8 and to_frame[ny][x]:
                    out_frame[y][x] = 1
                    out_colors[y][x] = to_colors[ny][x]

        return out_frame, out_colors

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
            pixels, colors, until = self.manual_override
            if time.time() <= until:
                self.last_source = "manual"
                return pixels, colors
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
        if payload.frame is not None:
            frame = payload.frame
        else:
            frame, generated_colors = render_text_with_colors(
                payload.text,
                font_size=payload.font_size,
                char_colors=payload.char_colors or None,
                base_color=payload.default_color,
                x_offset=payload.x_offset,
                y_offset=payload.y_offset,
            )
            payload.color_frame = generated_colors

        color_frame = payload.color_frame or blank_color_frame(32, 8)

        settings = selected["settings"] or {}
        transition_direction = settings.get("transition_direction", "down")
        if transition_direction not in {"down", "up"}:
            transition_direction = "down"
        transition_ms = max(0, min(2000, _safe_int(settings.get("transition_ms", 350), 350)))

        if self.transition_state:
            state = self.transition_state
            if state.get("to_key") == selected["key"] and state.get("to_frame") == frame:
                elapsed = (time.time() - state["start_time"]) * 1000.0
                if elapsed < state["duration_ms"]:
                    progress = elapsed / max(state["duration_ms"], 1)
                    return self._slide_vertical(
                        state["from_frame"],
                        state["from_colors"],
                        state["to_frame"],
                        state["to_colors"],
                        progress,
                        state["direction"],
                    )
                self.transition_state = None

        target_changed = (
            self.last_target_key != selected["key"]
            or self.last_target_frame != frame
            or self.last_target_colors != color_frame
        )

        if transition_ms > 0 and self.last_target_key is not None and target_changed:
            self.transition_state = {
                "from_frame": [row[:] for row in self.last_frame],
                "from_colors": [row[:] for row in self.last_color_frame],
                "to_frame": [row[:] for row in frame],
                "to_colors": [row[:] for row in color_frame],
                "to_key": selected["key"],
                "start_time": time.time(),
                "duration_ms": transition_ms,
                "direction": transition_direction,
            }
            self.last_target_key = selected["key"]
            self.last_target_frame = [row[:] for row in frame]
            self.last_target_colors = [row[:] for row in color_frame]
            return self._slide_vertical(
                self.transition_state["from_frame"],
                self.transition_state["from_colors"],
                self.transition_state["to_frame"],
                self.transition_state["to_colors"],
                0.0,
                transition_direction,
            )

        self.last_target_key = selected["key"]
        self.last_target_frame = [row[:] for row in frame]
        self.last_target_colors = [row[:] for row in color_frame]
        return frame, color_frame
