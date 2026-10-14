import asyncio
import logging
import math
import time
import threading
from copy import deepcopy
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import ModuleConfig
from app.modules.base import ModulePayload
from app.modules.btc import BTCModule
from app.modules.clock import ClockModule
from app.modules.weather import WeatherModule
from app.modules.textbox import TextBoxModule
from app.modules.bitmap import BitmapModule
from app.modules.animations import AnimationsModule
from app.services.led_driver import LEDDriver
from app.services.frame_pacer import FramePacer
from app.services.led_mapper import LEDMapper
from app.services.colors import parse_hex_color
from app.services.animations import ANIMATION_FACTORIES
from app.services.rendering import blank_color_frame, render_text_with_colors
from app.services.bitmap_loader import BitmapLoader
from app.config import get_settings
from app.services.playlist import Playlist
from app.services.assets import asset_frame

MODULE_REGISTRY = {
    "clock": ClockModule(),
    "btc": BTCModule(),
    "weather": WeatherModule(),
    "textbox": TextBoxModule(),
    "bitmap": BitmapModule(),
    "animations": AnimationsModule(),
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


def _clock_border_path(width: int = 32, height: int = 8) -> list[tuple[int, int]]:
    path: list[tuple[int, int]] = []
    for x in range(width):
        path.append((x, 0))
    for y in range(1, height):
        path.append((width - 1, y))
    for x in range(width - 2, -1, -1):
        path.append((x, height - 1))
    for y in range(height - 2, 0, -1):
        path.append((0, y))
    return path


def _clock_border_progress(seconds: int, mode: str, path_len: int) -> int:
    seconds = max(0, min(59, seconds))
    if path_len <= 0:
        return 0
    if mode == "two_forward_one_back":
        steps = round((seconds / 59) * (path_len * 3))
        cycles, rest = divmod(steps, 3)
        progress = cycles
        if rest == 1:
            progress += 1
        elif rest == 2:
            progress += 2
    else:
        progress = round((seconds / 59) * path_len)
    return max(0, min(path_len, progress))

class DisplayService:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        led_driver: LEDDriver,
        mapper: LEDMapper,
        cache_provider: Callable[[], dict],
        fps: int,
        bitmap_loader: BitmapLoader,
        asset_store=None,
    ):
        self._logger = logging.getLogger(__name__)
        self.session_factory = session_factory
        self.led_driver = led_driver
        self.mapper = mapper
        self.cache_provider = cache_provider
        self.frame_delay = 1 / fps
        self.bitmap_loader = bitmap_loader
        self.asset_store = asset_store
        self.brightness_lock = asyncio.Lock()
        self.time_stage = None
        self.time_stage_config = None
        self.astronomy_data = {}
        self.astronomy_error = None
        self._astronomy_task = None
        self._astronomy_changed = asyncio.Event()
        self._stage_preview = None
        self._stage_counted_generation = -1
        self._was_sleeping = False
        self._effective_brightness = None
        snapshot = led_driver.get_debug_snapshot(poll=False)
        initial = snapshot.get("brightness") if isinstance(snapshot, dict) else None
        self._day_brightness = initial if type(initial) is int else get_settings().led_brightness
        self._stage_render_error = None
        self._bitcoin_directors = {}
        self._bitcoin_visit = None
        self._bitcoin_generation = None
        self._bitcoin_error = None
        self._weather_directors = {}
        self._weather_visit = None
        self._weather_generation = None
        self._weather_error = None
        self._preview_sky_cache = {}
        self._preview_sky_lock = threading.Lock()
        self.playlist = Playlist()
        self._play_once = None
        self._asset_data = None
        self._asset_identity = None
        self._slot_generation = -1
        self.target_fps = fps
        self._running = False
        self._task: asyncio.Task | None = None
        self._pacer: FramePacer | None = None
        self._last_mapping_revision: int | None = None
        self._first_frame = True
        self.manual_override: tuple[list[list[int]], list[list[tuple[int, int, int] | None]], float] | None = None
        self.debug_override: tuple[str, float, float] | None = None
        self._manual_deadline = 0.0
        self._debug_deadline = 0.0

        self.last_frame_ts: float | None = None
        self.last_loop_error: str | None = None
        self.last_loop_error_at: float | None = None
        self.last_loop_work_ms: float | None = None
        self.last_loop_sleep_ms: float | None = None
        self.last_loop_total_ms: float | None = None
        self.last_led_write_ms: float | None = None
        self.last_led_frame_sent: bool | None = None
        self.unchanged_frame_skips = 0
        self.last_module_query_ms: float | None = None
        self.last_module_query_cache_hit: bool | None = None
        self.frame_counter = 0
        self.started_at = time.time()
        self._started_monotonic = time.monotonic()
        self.last_source = "module"
        self.last_module_key: str | None = None
        self.last_frame: list[list[int]] = [[0 for _ in range(32)] for _ in range(8)]
        self.last_color_frame: list[list[tuple[int, int, int] | None]] = blank_color_frame(32, 8)
        self.transition_state: dict | None = None
        self.last_target_key: str | None = None
        self.last_target_frame: list[list[int]] = [[0 for _ in range(32)] for _ in range(8)]
        self.last_target_colors: list[list[tuple[int, int, int] | None]] = blank_color_frame(32, 8)
        self.clock_border_path = _clock_border_path(32, 8)
        self.last_cache_snapshot: dict = {}
        self.last_cache_snapshot_ts: float | None = None
        self._module_rows_cache: list | None = None
        self._module_rows_cache_perf_ts: float | None = None
        self.module_rows_cache_ttl_s = 0.5
        self.last_render_debug: dict = {
            "module_key": None,
            "module_text": None,
            "module_settings": {},
            "panel_values": {},
            "cache_missing_keys": [],
            "cache_has_any_values": False,
            "updated_at": None,
        }

    @staticmethod
    def _module_cache_keys(module_key: str | None) -> list[str]:
        common_keys = ["weather_source", "btc_error", "weather_error", "dht_error"]
        if module_key == "btc":
            return [
                "btc_eur",
                "btc_trend",
                "btc_block_height",
                "btc_updated_at",
                "btc_block_height_updated_at",
                "btc_block_height_error",
            ] + common_keys
        if module_key == "weather":
            return [
                "weather_outdoor_temp",
                "weather_indoor_temp",
                "weather_indoor_humidity",
                "weather_updated_at",
                "dht_updated_at",
                "dht_backend",
                "dht_last_attempt_at",
            ] + common_keys
        return common_keys

    def _update_live_debug(self, module_key: str | None, settings: dict, cache: dict, payload: ModulePayload | None = None):
        keys = self._module_cache_keys(module_key)
        panel_values = {key: cache.get(key) for key in keys}
        self.last_render_debug = {
            "module_key": module_key,
            "module_text": payload.text if payload else None,
            "module_settings": settings,
            "panel_values": panel_values,
            "cache_missing_keys": [key for key in keys if key not in cache],
            "cache_has_any_values": any(value is not None for value in panel_values.values()),
            "updated_at": time.time(),
        }

    async def start(self):
        if self._task and not self._task.done():
            return
        self._first_frame = True
        self._running = True
        if self.time_stage and (not self._astronomy_task or self._astronomy_task.done()):
            self._astronomy_task = asyncio.create_task(self._astronomy_loop())
        self._task = asyncio.create_task(self._loop())

    def _stage_now(self):
        return datetime.now(ZoneInfo(self.time_stage_config["timezone"]))

    def configure_time_stage(self, config):
        from app.services.time_stage.engine import TimeStageEngine
        changed_location = not self.time_stage_config or any(self.time_stage_config.get(k) != config.get(k) for k in ("location", "timezone"))
        self.time_stage_config = config
        if self.time_stage is None:
            self.time_stage = TimeStageEngine(config)
        else:
            self.time_stage.set_config(config)
        if changed_location:
            self.astronomy_data = {}
        self._astronomy_changed.set()

    def time_stage_location(self, config=None):
        location = (config or self.time_stage_config)["location"]
        system = get_settings()
        return {"latitude": location["latitude"] if location["source"] == "custom" else system.weather_lat,
                "longitude": location["longitude"] if location["source"] == "custom" else system.weather_lon,
                "source": location["source"]}

    async def _astronomy_loop(self):
        from app.services.time_stage.astronomy import calculate
        while self._running:
            try:
                self._astronomy_changed.clear()
                config = self.time_stage_config
                location = self.time_stage_location()
                result = await asyncio.to_thread(calculate, self._stage_now(), location["latitude"], location["longitude"])
                # A slow calculation must not publish data for a superseded location.
                if config is self.time_stage_config:
                    self.astronomy_data = result
                    self.astronomy_error = None
            except Exception as exc:
                self.astronomy_error = str(exc)
                self._logger.exception("Time-Stage astronomy calculation failed")
            try:
                await asyncio.wait_for(self._astronomy_changed.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass

    def time_stage_status(self):
        if not self.time_stage:
            return {"enabled": False}
        status = self.time_stage.status(self._stage_now(), time.monotonic())
        status.update(day_brightness=self._day_brightness, effective_brightness=self._effective_brightness,
                      astronomy_error=self.astronomy_error, render_error=self._stage_render_error,
                      physical_preview=bool(self._stage_preview))
        return status

    def preview_for_browser(self, key, now, elapsed=0, config=None):
        from app.services.time_stage.celestial import KEYS
        info = self.preview_astronomy(now, config) if key in KEYS else None
        return self.render_time_stage_preview(key, now, elapsed, info=info, config=config)

    def preview_astronomy(self, now, config=None):
        from app.services.time_stage.astronomy import calculate
        location = self.time_stage_location(config)
        stamp = now.replace(second=0, microsecond=0).isoformat()
        identity = (stamp, location["latitude"], location["longitude"])
        with self._preview_sky_lock:
            if identity not in self._preview_sky_cache:
                self._preview_sky_cache[identity] = calculate(now, location["latitude"], location["longitude"])
                if len(self._preview_sky_cache) > 8:
                    self._preview_sky_cache.pop(next(iter(self._preview_sky_cache)))
            return self._preview_sky_cache[identity]

    def render_time_stage_preview(self, key, now, elapsed=0, info=None, config=None):
        from app.services.time_stage import SCENES, render_scene
        from app.services.time_stage.celestial import KEYS, render_celestial
        from app.services.time_stage.core import Canvas, shade
        config = config or self.time_stage_config
        if key not in SCENES and key not in KEYS:
            raise ValueError("Unbekannte Time-Stage-Szene")
        elapsed = float(elapsed)
        if not math.isfinite(elapsed):
            raise ValueError("Ungültige Animationszeit")
        elapsed = max(0, elapsed)
        try:
            if key in KEYS:
                event = config["events"][key]
                payload = render_celestial(key, now, elapsed, event["duration_seconds"], self.astronomy_data if info is None else info, event["panels"])
            else:
                scene = SCENES[key]
                speed = {"calm": .45, "normal": 1.0, "lively": 1.3}[config["intensity"]]
                payload = render_scene(key, now, elapsed if scene.events else elapsed * speed)
                if not scene.events and config["minute_transition"] and now.second == 0 and now.microsecond < 700_000:
                    # Scatter the old arrangement and settle into the actual new time.
                    phase = now.microsecond / 700_000
                    transformed = Canvas()
                    for y, row in enumerate(payload.color_frame):
                        for x, color in enumerate(row):
                            if color is not None:
                                offset = int((1 - phase) * ((x * 7 + y * 13) % 9 - 4))
                                transformed.pixel(x, y + offset, shade(color, .5 + phase * .5))
                    payload = transformed.payload(now, key)
            if config["color"] and key in SCENES and not SCENES[key].events:
                tone = parse_hex_color(config["color"], (110, 225, 255))
                payload.color_frame = [[tuple(round(c * max(rgb) / 255) for c in tone) if rgb else None for rgb in row] for row in payload.color_frame]
            self._stage_render_error = None
            return payload
        except Exception as exc:
            if self._stage_render_error != str(exc):
                self._logger.exception("Time-Stage scene failed; using plain clock")
            self._stage_render_error = str(exc)
            fallback = Canvas()
            fallback.clock(now)
            return fallback.payload(now, "fallback")

    def preview_time_stage(self, key, confirm_wake=False, config=None, info=None):
        from app.services.time_stage import SCENES
        from app.services.time_stage.celestial import KEYS
        if not self.time_stage or key not in SCENES and key not in KEYS:
            raise ValueError("Unbekannte Time-Stage-Szene")
        if self.time_stage.sleep_state(self._stage_now())["active"]:
            raise ValueError("Schlafmodus aktiv. Bitte zuerst ausdrücklich auf Wach umschalten.")
        config = config or self.time_stage_config
        duration = config["events"][key]["duration_seconds"] if key in KEYS else SCENES[key].duration if SCENES[key].events else config["duration_seconds"]
        self._start_live_preview({"key": key, "config": deepcopy(config), "info": deepcopy(info),
                                  "kind": "time-stage", "confirm_wake": False}, duration)

    def preview_bitcoin(self, settings):
        from app.services.bitcoin_stage import Director
        if self.time_stage and self.time_stage.sleep_state(self._stage_now())["active"]:
            raise ValueError("Schlafmodus aktiv. Bitte zuerst ausdrücklich auf Wach umschalten.")
        visit = Director().begin(settings, dict(self.cache_provider() or {}), preview=True)
        self._start_live_preview({"kind": "bitcoin", "visit": visit, "confirm_wake": False}, visit.duration)

    def _start_live_preview(self, preview, duration):
        """One preview slot shared by stages; replacement never queues or saves."""
        now = time.monotonic()
        if self._stage_preview:
            self._finish_stage_preview(now)
        self._stage_preview = {**preview, "start": now, "end": now + duration}
        self.transition_state = None

    def preview_weather(self, settings):
        from app.services.weather_stage import Director
        if self.time_stage and self.time_stage.sleep_state(self._stage_now())["active"]:
            raise ValueError("Schlafmodus aktiv. Bitte zuerst ausdrücklich auf Wach umschalten.")
        visit = Director().begin(settings, dict(self.cache_provider() or {}), preview=True)
        self._start_live_preview({"kind": "weather", "visit": visit, "confirm_wake": False}, visit.duration)

    def _finish_stage_preview(self, now):
        delta = now - self._stage_preview["start"]
        if self.playlist.current is not None:
            self._shift_slot_generation(self.playlist.started, delta)
            self.playlist.started += delta
            self.playlist.deadline += delta
        if self._play_once:
            self._shift_slot_generation(self._play_once["start"], delta)
            self._play_once["start"] += delta
            self._play_once["end"] += delta
        if self.time_stage:
            if self.time_stage.active:
                self.time_stage.active["start"] += delta
                self.time_stage.active["end"] += delta
            if self.time_stage._last_clock is not None:
                self.time_stage._last_clock += delta
        if self.manual_override:
            pixels, colors, until = self.manual_override
            self.manual_override = (pixels, colors, until + delta)
            self._manual_deadline += delta
        if self.debug_override:
            pattern, until, interval = self.debug_override
            self.debug_override = (pattern, until + delta, interval)
            self._debug_deadline += delta
        self._stage_preview = None

    def _shift_slot_generation(self, started, delta):
        # Preserve visit identity when paused playback resumes: no new rotation.
        for field in ("_slot_generation", "_bitcoin_generation", "_weather_generation"):
            generation = getattr(self, field)
            if generation and generation[1] == started:
                setattr(self, field, (generation[0], started + delta))
        if self._asset_identity and self._asset_identity[2] == started:
            self._asset_identity = (*self._asset_identity[:2], started + delta)

    def _stage_target(self, payload, source="time-stage"):
        self.last_source = source
        self.last_module_key = str(payload.scene_key) if source in ("bitcoin-preview", "weather-preview") else "time-stage:" + str(payload.scene_key)
        self.last_target_key = self.last_module_key
        self.last_target_frame = [row[:] for row in payload.frame]
        self.last_target_colors = [row[:] for row in payload.color_frame]
        self.transition_state = None
        self._update_live_debug(self.last_module_key, {}, {}, payload)
        return payload.frame, payload.color_frame

    def _render_bitcoin_visit(self, visit, elapsed):
        from app.services.bitcoin_stage import render
        try:
            payload = render(visit, elapsed)
            self._bitcoin_error = None
            return payload
        except Exception as exc:
            if self._bitcoin_error != str(exc):
                self._logger.exception("Bitcoin story failed; keeping a readable data fallback")
            self._bitcoin_error = str(exc)
            from app.services.time_stage.core import Canvas
            canvas = Canvas()
            value = visit.infos[0]["value"]
            canvas.text(value, max(0, (32-len(value)*4+1)//2), 1, (255, 190, 75))
            return ModulePayload(text=value, frame=[[int(rgb is not None) for rgb in row] for row in canvas.colors],
                                 color_frame=canvas.colors, scene_key="bitcoin:fallback")

    async def _apply_stage_brightness(self):
        async with self.brightness_lock:
            asleep = self.time_stage.sleep_state(self._stage_now())["active"]
            bypass = self._stage_preview and self._stage_preview["confirm_wake"]
            wanted = self.time_stage_config["sleep"]["brightness"] if asleep and not bypass else self._day_brightness
            if wanted != self._effective_brightness:
                try:
                    await asyncio.to_thread(self.led_driver.set_brightness, wanted)
                except OSError as exc:
                    self._logger.warning("Time-Stage brightness deferred: %s", exc)
                self._effective_brightness = wanted

    def _render_weather_visit(self, visit, elapsed):
        from app.services.weather_stage import render
        try:
            payload = render(visit, elapsed)
            self._weather_error = None
            return payload
        except Exception as exc:
            if self._weather_error != str(exc):
                self._logger.exception("Weather story failed; keeping a readable data fallback")
            self._weather_error = str(exc)
            from app.services.time_stage.core import Canvas
            canvas = Canvas()
            value = visit.infos[0]["value"]
            canvas.text(value, max(0, (32-len(value)*4+1)//2), 1, (100, 220, 230))
            return ModulePayload(text=value, frame=[[int(rgb is not None) for rgb in row] for row in canvas.colors],
                                 color_frame=canvas.colors, scene_key="weather:fallback")

    def play_once(self, module):
        now = time.monotonic()
        row = {"id": module.id, "key": module.key, "settings": dict(module.settings or {}), "duration_seconds": module.duration_seconds}
        self._play_once = {"row": row, "start": now, "end": now + module.duration_seconds}
        identity = self.playlist.identity(row)
        self.playlist.visits[identity] = self.playlist.visits.get(identity, 0) + 1
        self.playlist.last_priority[identity] = now
        self._asset_identity = None

    @staticmethod
    def _transition(from_frame, from_colors, to_frame, to_colors, progress, direction):
        if direction in {"up", "down"}:
            return DisplayService._slide_vertical(from_frame, from_colors, to_frame, to_colors, progress, direction)
        frame = [[0] * 32 for _ in range(8)]
        colors = blank_color_frame(32, 8)
        for y in range(8):
            for x in range(32):
                old = from_colors[y][x] or (80, 80, 80) if from_frame[y][x] else (0, 0, 0)
                new = to_colors[y][x] or (80, 80, 80) if to_frame[y][x] else (0, 0, 0)
                if direction == "dissolve":
                    rank = (((x * 73 + y * 37) % 256) + 1) / 256
                    color = new if progress >= rank else old
                else:
                    # Smooth crossfade: never brighten beyond either source.
                    p = progress * progress * (3 - 2 * progress)
                    color = tuple(round(a * (1 - p) + b * p) for a, b in zip(old, new))
                if any(color):
                    frame[y][x], colors[y][x] = 1, color
        return frame, colors

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self._astronomy_task:
            self._astronomy_task.cancel()
            await asyncio.gather(self._astronomy_task, return_exceptions=True)

    async def _get_enabled_module_rows(self):
        now_perf = time.perf_counter()
        if (
            self._module_rows_cache is not None
            and self._module_rows_cache_perf_ts is not None
            and (now_perf - self._module_rows_cache_perf_ts) < self.module_rows_cache_ttl_s
        ):
            self.last_module_query_ms = 0.0
            self.last_module_query_cache_hit = True
            return self._module_rows_cache

        query_start = time.perf_counter()
        async with self.session_factory() as db:
            rows = (
                await db.execute(
                    ModuleConfig.__table__.select()
                    .where(ModuleConfig.enabled.is_(True))
                    .order_by(ModuleConfig.sort_order.asc(), ModuleConfig.id.asc())
                )
            ).mappings().all()

        self._module_rows_cache = rows
        self._module_rows_cache_perf_ts = time.perf_counter()
        self.last_module_query_ms = round((self._module_rows_cache_perf_ts - query_start) * 1000, 3)
        self.last_module_query_cache_hit = False
        return rows

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
        self._manual_deadline = time.monotonic() + seconds

    def set_manual_pixels(self, pixels: list[list[int]], seconds: int):
        color_frame = blank_color_frame(32, 8)
        for y in range(8):
            for x in range(32):
                if pixels[y][x]:
                    color_frame[y][x] = (240, 240, 240)
        self.manual_override = (pixels, color_frame, time.time() + seconds)
        self._manual_deadline = time.monotonic() + seconds

    def set_brightness(self, value: int):
        self._day_brightness = value
        asleep = self.time_stage and self.time_stage.sleep_state(self._stage_now())["active"]
        bypass = self._stage_preview and self._stage_preview["confirm_wake"]
        effective = self.time_stage_config["sleep"]["brightness"] if asleep and not bypass else value
        self.led_driver.set_brightness(effective)
        self._effective_brightness = effective

    def set_debug_pattern(self, pattern: str, seconds: int, interval_ms: int = 250):
        self.debug_override = (pattern, time.time() + seconds, max(interval_ms / 1000.0, 0.05))
        self._debug_deadline = time.monotonic() + seconds

    def clear_debug_pattern(self):
        self.debug_override = None

    def clear_manual_override(self):
        self.manual_override = None

    def get_preview_frame(self) -> list[list[int]]:
        return [row[:] for row in self.last_frame]

    def get_preview_colors(self) -> list[list[tuple[int, int, int] | None]]:
        return [row[:] for row in self.last_color_frame]

    def get_status(self) -> dict:
        uptime = max(time.monotonic() - self._started_monotonic, 1)
        return {
            "running": self._running,
            "task_alive": bool(self._task and not self._task.done()),
            "target_fps": self.target_fps,
            "missed_render_deadlines": self._pacer.missed_deadlines if self._pacer else 0,
            "fps_measurement": "render_iterations_lifetime_average_not_display_fps",
            "actual_fps": round(self.frame_counter / uptime, 2),
            "last_frame_ts": self.last_frame_ts,
            "last_loop_error": self.last_loop_error,
            "last_loop_error_at": self.last_loop_error_at,
            "last_loop_work_ms": self.last_loop_work_ms,
            "last_loop_sleep_ms": self.last_loop_sleep_ms,
            "last_loop_total_ms": self.last_loop_total_ms,
            "last_led_write_ms": self.last_led_write_ms,
            "last_led_frame_sent": self.last_led_frame_sent,
            "unchanged_frame_skips": self.unchanged_frame_skips,
            "last_module_query_ms": self.last_module_query_ms,
            "last_module_query_cache_hit": self.last_module_query_cache_hit,
            "module_rows_cache_ttl_s": self.module_rows_cache_ttl_s,
            "last_source": self.last_source,
            "last_module": self.last_module_key,
            "debug_active": bool(self.debug_override),
            "debug_pattern": self.debug_override[0] if self.debug_override else None,
            "debug_until": self.debug_override[1] if self.debug_override else None,
            "manual_active": bool(self.manual_override),
            "manual_until": self.manual_override[2] if self.manual_override else None,
            "cache_snapshot_ts": self.last_cache_snapshot_ts,
            "cache_snapshot_keys": sorted(list(self.last_cache_snapshot.keys())),
            "time_stage": self.time_stage_status(),
            "bitcoin_stage": {
                "style": self._bitcoin_visit.style if self._bitcoin_visit else None,
                "infos": self._bitcoin_visit.infos if self._bitcoin_visit else [],
                "duration": self._bitcoin_visit.duration if self._bitcoin_visit else None,
                "error": self._bitcoin_error,
            },
            "weather_stage": {
                "style": self._weather_visit.style if self._weather_visit else None,
                "infos": self._weather_visit.infos if self._weather_visit else [],
                "duration": self._weather_visit.duration if self._weather_visit else None,
                "error": self._weather_error,
            },
        }

    def get_live_data_snapshot(self) -> dict:
        cache = self.last_cache_snapshot or {}
        return {
            "btc_eur": cache.get("btc_eur"),
            "btc_trend": cache.get("btc_trend"),
            "btc_block_height": cache.get("btc_block_height"),
            "btc_block_height_updated_at": cache.get("btc_block_height_updated_at"),
            "btc_block_height_error": cache.get("btc_block_height_error"),
            "btc_updated_at": cache.get("btc_updated_at"),
            "btc_error": cache.get("btc_error"),
            "weather_temp": cache.get("weather_temp"),
            "weather_outdoor_temp": cache.get("weather_outdoor_temp"),
            "weather_indoor_temp": cache.get("weather_indoor_temp"),
            "weather_indoor_humidity": cache.get("weather_indoor_humidity"),
            "weather_updated_at": cache.get("weather_updated_at"),
            "weather_error": cache.get("weather_error"),
            "weather_source": cache.get("weather_source"),
            "dht_updated_at": cache.get("dht_updated_at"),
            "dht_error": cache.get("dht_error"),
            "dht_gpio_level": cache.get("dht_gpio_level"),
            "dht_last_attempt_at": cache.get("dht_last_attempt_at"),
            "dht_last_duration_ms": cache.get("dht_last_duration_ms"),
            "dht_raw_temperature": cache.get("dht_raw_temperature"),
            "dht_raw_humidity": cache.get("dht_raw_humidity"),
            "dht_backend": cache.get("dht_backend"),
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

    def _apply_clock_border_seconds(
        self,
        frame: list[list[int]],
        color_frame: list[list[tuple[int, int, int] | None]],
        settings: dict,
    ) -> tuple[list[list[int]], list[list[tuple[int, int, int] | None]]]:
        mode = str(settings.get("seconds_border_mode", "off")).strip().lower()
        if mode not in {"off", "linear", "two_forward_one_back", "dual_edge"}:
            mode = "off"
        if mode == "off":
            return frame, color_frame

        border_color = parse_hex_color(settings.get("seconds_border_color"), (60, 200, 255))
        tz_name = settings.get("timezone", get_settings().tz)
        try:
            now_sec = datetime.now(ZoneInfo(tz_name)).second
        except ZoneInfoNotFoundError:
            now_sec = datetime.now(ZoneInfo(get_settings().tz)).second

        progress = _clock_border_progress(now_sec, mode, len(self.clock_border_path))
        if progress <= 0:
            return frame, color_frame

        if mode == "dual_edge":
            half = len(self.clock_border_path) // 2
            left = progress // 2
            right = progress - left
            indices = set(range(left))
            indices.update(((half + idx) % len(self.clock_border_path)) for idx in range(right))
        else:
            indices = set(range(progress))

        for idx in indices:
            x, y = self.clock_border_path[idx]
            frame[y][x] = 1
            color_frame[y][x] = border_color

        return frame, color_frame

    async def _loop(self):
        self._pacer = FramePacer(self.target_fps, time.perf_counter())
        while self._running:
            loop_started = time.perf_counter()
            try:
                frame, color_frame = await self._get_next_frame()
                force_frame_send = bool(getattr(self.led_driver, "should_force_frame_send", lambda: False)())
                mapping_revision = getattr(self.mapper, "revision", 0)
                frame_changed = self._first_frame or force_frame_send or mapping_revision != self._last_mapping_revision or frame != self.last_frame or color_frame != self.last_color_frame
                if frame_changed:
                    index_to_color: dict[int, tuple[int, int, int]] = {}
                    for y, row in enumerate(frame):
                        for x, val in enumerate(row):
                            if not val:
                                continue
                            led_index = self.mapper.xy_to_index(x, y)
                            color = color_frame[y][x] if color_frame and color_frame[y][x] else (80, 80, 80)
                            index_to_color[led_index] = color

                    led_write_started = time.perf_counter()
                    self.led_driver.write_color_frame(index_to_color)
                    self.last_led_write_ms = round((time.perf_counter() - led_write_started) * 1000, 3)
                    self.last_led_frame_sent = True
                    self._first_frame = False
                    self._last_mapping_revision = mapping_revision
                else:
                    self.unchanged_frame_skips += 1
                    self.last_led_write_ms = 0.0
                    self.last_led_frame_sent = False
                self.last_frame = [row[:] for row in frame]
                self.last_color_frame = [row[:] for row in color_frame]
                self.last_frame_ts = time.time()
                self.last_loop_error = None
                self.frame_counter += 1
                work_elapsed = time.perf_counter() - loop_started
                sleep_s = self._pacer.next_delay(time.perf_counter())
                self.last_loop_work_ms = round(work_elapsed * 1000, 3)
                self.last_loop_sleep_ms = round(sleep_s * 1000, 3)
                self.last_loop_total_ms = round((work_elapsed + sleep_s) * 1000, 3)
                await asyncio.sleep(sleep_s if sleep_s > 0 else 0)
            except Exception as exc:
                # Keep the render task alive so the UI can still inspect serial/debug state.
                self.last_loop_error = str(exc)
                self.last_loop_error_at = time.time()
                self._logger.exception("Display render loop iteration failed")
                self.last_loop_work_ms = round((time.perf_counter() - loop_started) * 1000, 3)
                self.last_loop_sleep_ms = round(max(self.frame_delay, 0.1) * 1000, 3)
                self.last_loop_total_ms = round((self.last_loop_work_ms or 0) + (self.last_loop_sleep_ms or 0), 3)
                await asyncio.sleep(max(self.frame_delay, 0.1))
                self._pacer = FramePacer(self.target_fps, time.perf_counter())

    async def _get_next_frame(self) -> tuple[list[list[int]], list[list[tuple[int, int, int] | None]]]:
        bitcoin_cache = dict(self.cache_provider() or {})
        bitcoin_sleeping = bool(self.time_stage and self.time_stage.sleep_state(self._stage_now())["active"])
        for director in self._bitcoin_directors.values():
            director.observe(bitcoin_cache, time.time(), sleeping=bitcoin_sleeping)
        if self.time_stage:
            now_mono = time.monotonic()
            wall = self._stage_now()
            if self._stage_preview and now_mono >= self._stage_preview["end"]:
                self._finish_stage_preview(now_mono)
            await self._apply_stage_brightness()
            sleeping = self.time_stage.sleep_state(wall)["active"]
            if sleeping:
                if self._stage_preview:
                    self._finish_stage_preview(now_mono)
                from app.services.time_stage.core import Canvas
                self.time_stage.tick(wall, now_mono, boundary=False, astronomy=self.astronomy_data)
                if not self._was_sleeping:
                    self.playlist.current = None
                    self.playlist.deadline = 0
                    self._play_once = None
                    self.manual_override = self.debug_override = None
                self._was_sleeping = True
                canvas = Canvas()
                canvas.clock(wall, parse_hex_color(self.time_stage_config["sleep"]["color"], (255, 80, 12)))
                return self._stage_target(canvas.payload(wall, "sleep"), "sleep")
            self._was_sleeping = False
        if self._stage_preview:
            now_mono = time.monotonic()
            if now_mono >= self._stage_preview["end"]:
                self._finish_stage_preview(now_mono)
            else:
                preview = self._stage_preview
                if preview["kind"] == "bitcoin":
                    payload = self._render_bitcoin_visit(preview["visit"], now_mono - preview["start"])
                elif preview["kind"] == "weather":
                    payload = self._render_weather_visit(preview["visit"], now_mono - preview["start"])
                else:
                    config = preview["config"]
                    wall = datetime.now(ZoneInfo(config["timezone"]))
                    payload = self.render_time_stage_preview(preview["key"], wall, now_mono - preview["start"],
                                                             config=config, info=preview["info"])
                return self._stage_target(payload, preview["kind"] + "-preview")
        if self.debug_override:
            from app.services.patterns import PATTERN_FACTORIES

            pattern, until, interval = self.debug_override
            now = time.monotonic()
            if now <= self._debug_deadline and pattern in ANIMATION_FACTORIES:
                self.last_source = "debug"
                return ANIMATION_FACTORIES[pattern](now)
            if now <= self._debug_deadline and pattern in PATTERN_FACTORIES:
                self.last_source = "debug"
                tick = int(now / interval)
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
            if time.monotonic() <= self._manual_deadline:
                self.last_source = "manual"
                return pixels, colors
            self.manual_override = None

        rows = await self._get_enabled_module_rows()

        now = time.monotonic()
        if self._play_once and now >= self._play_once["end"]:
            # Resume with a fresh slot rather than jumping into a half-finished GIF.
            self._play_once = None
            self.playlist.deadline = now
            self._stage_counted_generation = self.playlist.generation
        if self.time_stage:
            rows = [row for row in rows if row["key"].split("-")[0] != "clock"]
            available = {self.playlist.identity(row) for row in rows}
            boundary = not self._play_once and (not rows or self.playlist.current not in available or now >= self.playlist.deadline)
            completed = boundary and self.playlist.current is not None and self._stage_counted_generation != self.playlist.generation
            if completed:
                self._stage_counted_generation = self.playlist.generation
            slot = self.time_stage.tick(self._stage_now(), now, boundary=boundary,
                                        completed=completed and self.playlist.slot_type == "regular",
                                        astronomy=self.astronomy_data, idle=not rows)
            if slot:
                elapsed = now - slot["start"]
                from app.services.time_stage import SCENES
                if slot["key"] == "craft_roman_scroll" and not slot.get("cycle_adjusted"):
                    from app.services.time_stage.craft import _roman
                    wall = self._stage_now()
                    cycle = (len(_roman(wall.hour)) + len(_roman(wall.minute)) + 4) * 4 / (5 * {"calm":.45,"normal":1,"lively":1.3}[self.time_stage_config["intensity"]])
                    extended = slot["start"] + math.ceil((slot["end"] - slot["start"]) / cycle) * cycle
                    self.time_stage.active.update(end=extended, cycle_adjusted=True)
                if slot["kind"] == "event":
                    elapsed *= SCENES[slot["key"]].duration / (slot["end"] - slot["start"])
                return self._stage_target(self.render_time_stage_preview(slot["key"], self._stage_now(), elapsed))
        if not rows and not self._play_once:
            self.last_source = "idle"
            return [[0 for _ in range(32)] for _ in range(8)], blank_color_frame(32, 8)

        selected = self._play_once["row"] if self._play_once else self.playlist.select(rows, now)
        kind = selected["key"].split("-")[0]
        module = MODULE_REGISTRY.get(kind)
        if not module and kind != "asset":
            self.last_source = "module"
            self.last_module_key = None
            self._update_live_debug(None, {}, {}, None)
            return [[0 for _ in range(32)] for _ in range(8)], blank_color_frame(32, 8)

        self.last_source = "module"
        self.last_module_key = selected["key"]
        settings = dict(selected["settings"] or {})
        slot_start = self._play_once["start"] if self._play_once else self.playlist.started
        settings["_elapsed"] = now - slot_start
        settings["_visit"] = self.playlist.visits.get(self.playlist.identity(selected), 1) - 1
        generation = (selected["key"], slot_start)
        if self._slot_generation != generation:
            self._slot_generation = generation
            if kind == "textbox" and settings.get("text_mode") == "scroll":
                _, widths, speed = TextBoxModule.scroll_cycle(settings)
                cycle = sum(widths) / speed
                if self._play_once:
                    self._play_once["end"] = slot_start + math.ceil(selected["duration_seconds"] / cycle) * cycle
                else:
                    self.playlist.finish_cycle(cycle)

        live_cache = dict(self.cache_provider() or {})
        target_key = selected["key"]
        self.last_cache_snapshot = live_cache
        self.last_cache_snapshot_ts = time.time()

        if kind == "btc" and settings.get("bitcoin_stage", True):
            from app.services.bitcoin_stage import Director
            identity = self.playlist.identity(selected)
            if identity not in self._bitcoin_directors:
                if len(self._bitcoin_directors) >= 128:
                    self._bitcoin_directors.pop(next(iter(self._bitcoin_directors)))
                self._bitcoin_directors[identity] = Director()
                self._bitcoin_directors[identity].observe(live_cache, time.time())
            if self._bitcoin_generation != generation:
                self._bitcoin_generation = generation
                self._bitcoin_visit = self._bitcoin_directors[identity].begin(settings, live_cache, preview=bool(settings.get("_bitcoin_preview")))
                deadline = slot_start + self._bitcoin_visit.duration
                if self._play_once: self._play_once["end"] = deadline
                else: self.playlist.deadline = deadline
            payload = self._render_bitcoin_visit(self._bitcoin_visit, now-slot_start)
            self._update_live_debug(selected["key"], settings, live_cache, payload)
            # Choreography is complete; do not layer generic per-value transitions.
            self.transition_state = None
            self.last_target_key = selected["key"]
            self.last_target_frame = [row[:] for row in payload.frame]
            self.last_target_colors = [row[:] for row in payload.color_frame]
            return payload.frame, payload.color_frame

        if kind == "weather" and settings.get("weather_stage", True):
            from app.services.weather_stage import Director
            identity = self.playlist.identity(selected)
            if identity not in self._weather_directors:
                if len(self._weather_directors) >= 128:
                    self._weather_directors.pop(next(iter(self._weather_directors)))
                self._weather_directors[identity] = Director()
            if self._weather_generation != generation:
                self._weather_generation = generation
                self._weather_visit = self._weather_directors[identity].begin(settings, live_cache)
                deadline = slot_start + self._weather_visit.duration
                if self._play_once:
                    self._play_once["end"] = deadline
                else:
                    self.playlist.deadline = deadline
            payload = self._render_weather_visit(self._weather_visit, now-slot_start)
            self._update_live_debug(selected["key"], settings, live_cache, payload)
            self.transition_state = None
            self.last_target_key = selected["key"]
            self.last_target_frame = [row[:] for row in payload.frame]
            self.last_target_colors = [row[:] for row in payload.color_frame]
            return payload.frame, payload.color_frame

        if kind == "asset":
            identity = (selected["key"], settings.get("asset_id"), slot_start)
            if self._asset_identity != identity:
                try:
                    self._asset_data = await asyncio.to_thread(self.asset_store.load, settings.get("asset_id"))
                except (ValueError, OSError, AttributeError):
                    self._asset_data = None
                self._asset_identity = identity
                if self._asset_data:
                    from app.services.asset_editing import playback_timing
                    timing = playback_timing(self._asset_data['cycle_seconds'], selected['duration_seconds'],
                                             settings.get('speed',1),settings.get('playback_mode','limit'))
                    deadline = slot_start + timing['duration']
                    if self._play_once:
                        self._play_once["end"] = deadline
                    else:
                        self.playlist.deadline = deadline
            if self._asset_data:
                frame, color_frame = asset_frame(self._asset_data, now - slot_start, settings.get("speed", 1))
            else:
                frame, color_frame = [[0] * 32 for _ in range(8)], blank_color_frame(32, 8)
            self._update_live_debug(selected["key"], settings, live_cache, None)
        elif kind == "bitmap":
            try:
                file_path = str(settings.get("file", "")).strip()
                bitmap = self.bitmap_loader.load(file_path)
                frame, color_frame = self.bitmap_loader.render_window(
                    bitmap,
                    scroll_direction=str(settings.get("scroll_direction", "top_to_bottom")),
                    scroll_speed=max(0.25, float(settings.get("scroll_speed", 2.0))),
                )
                color_mode = str(settings.get("color_mode", "bitmap")).strip().lower()
                if color_mode not in {"bitmap", "solid"}:
                    color_mode = "bitmap"
                bitmap_color = settings.get("color")
                if color_mode == "solid" and bitmap_color:
                    parsed_color = parse_hex_color(bitmap_color, (245, 245, 245))
                    for y in range(8):
                        for x in range(32):
                            if frame[y][x]:
                                color_frame[y][x] = parsed_color
                elif bitmap.is_monochrome and bitmap_color:
                    parsed_color = parse_hex_color(bitmap_color, (245, 245, 245))
                    for y in range(8):
                        for x in range(32):
                            if frame[y][x] and color_frame[y][x] is not None:
                                color_frame[y][x] = parsed_color
            except (ValueError, TypeError):
                frame = [[0 for _ in range(32)] for _ in range(8)]
                color_frame = blank_color_frame(32, 8)
            self._update_live_debug(selected["key"], settings, live_cache, None)
        else:
            payload: ModulePayload = await module.render(settings, live_cache)
            if payload.scene_key:
                target_key += ":" + payload.scene_key
            self._update_live_debug(selected["key"], settings, live_cache, payload)
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
                    char_spacing=payload.char_spacing,
                )
                payload.color_frame = generated_colors

            color_frame = payload.color_frame or blank_color_frame(32, 8)

        if kind == "clock":
            frame = [row[:] for row in frame]
            color_frame = [row[:] for row in color_frame]
            frame, color_frame = self._apply_clock_border_seconds(frame, color_frame, settings)

        transition_direction = settings.get("transition_direction", "down")
        if transition_direction not in {"down", "up"}:
            transition_direction = "down"
        transition_ms = max(0, min(2000, _safe_int(settings.get("transition_ms", 350), 350)))
        effect = settings.get("transition_effect", "fade")
        if effect in {"fade", "dissolve"}:
            transition_direction = effect
        elif effect == "none":
            transition_ms = 0

        if self.transition_state:
            state = self.transition_state
            if state.get("to_key") == target_key:
                elapsed = (time.monotonic() - state["start_time"]) * 1000.0
                if elapsed < state["duration_ms"]:
                    # Keep the transition timeline while the incoming animation
                    # continues, instead of restarting it for every new frame.
                    self.last_target_frame = [row[:] for row in frame]
                    self.last_target_colors = [row[:] for row in color_frame]
                    progress = elapsed / max(state["duration_ms"], 1)
                    return self._transition(
                        state["from_frame"],
                        state["from_colors"],
                        frame,
                        color_frame,
                        progress,
                        state["direction"],
                    )
            self.transition_state = None

        target_changed = self.last_target_key != target_key

        if transition_ms > 0 and self.last_target_key is not None and target_changed:
            self.transition_state = {
                "from_frame": [row[:] for row in self.last_target_frame],
                "from_colors": [row[:] for row in self.last_target_colors],
                "to_frame": [row[:] for row in frame],
                "to_colors": [row[:] for row in color_frame],
                "to_key": target_key,
                "start_time": time.monotonic(),
                "duration_ms": transition_ms,
                "direction": transition_direction,
            }
            self.last_target_key = target_key
            self.last_target_frame = [row[:] for row in frame]
            self.last_target_colors = [row[:] for row in color_frame]
            return self._transition(
                self.transition_state["from_frame"],
                self.transition_state["from_colors"],
                self.transition_state["to_frame"],
                self.transition_state["to_colors"],
                0.0,
                transition_direction,
            )

        self.last_target_key = target_key
        self.last_target_frame = [row[:] for row in frame]
        self.last_target_colors = [row[:] for row in color_frame]
        return frame, color_frame
