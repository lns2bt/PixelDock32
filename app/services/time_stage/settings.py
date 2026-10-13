"""Validated Time-Stage preferences and non-destructive legacy migration."""

from copy import deepcopy
from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select

from app.models import ModuleConfig, TimeStagePreference

Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
EVENT_CATEGORIES = (
    "hour", "half", "quarter", "midnight", "sunrise", "sunset", "moonrise",
    "moonset", "golden_hour", "solar_noon", "full_moon", "new_moon", "equinox", "solstice",
)
PRIMARY_EVENTS = {"hour", "half", "quarter", "midnight"}
DEFAULT_ENABLED_EVENTS = PRIMARY_EVENTS | {"sunrise", "sunset", "moonrise", "moonset"}


def _normal_keys():
    from app.services.time_stage import NORMAL_SCENES
    return [scene.key for scene in NORMAL_SCENES]


def _event_keys():
    from app.services.time_stage import SCENES
    from app.services.time_stage.celestial import KEYS
    return {key for key, scene in SCENES.items() if scene.events} | set(KEYS)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)


class Event(StrictModel):
    enabled: bool = True
    scenes: list[str] = Field(default_factory=list, min_length=1, max_length=64)
    duration_seconds: int = Field(default=8, ge=6, le=60)
    panels: list[str] = Field(default_factory=lambda: ["time"], min_length=1, max_length=10)

    @field_validator("scenes")
    @classmethod
    def valid_scenes(cls, value):
        if len(value) != len(set(value)) or any(key not in _event_keys() for key in value):
            raise ValueError("Unknown or duplicate event scene")
        return value

    @field_validator("panels")
    @classmethod
    def valid_panels(cls, value):
        from app.services.time_stage.celestial import PANELS
        allowed = set(PANELS)
        if len(value) != len(set(value)) or any(panel not in allowed for panel in value):
            raise ValueError("Unknown or duplicate event panel")
        return value


def _default_events():
    from app.services.time_stage import SCENES
    result = {}
    for category in EVENT_CATEGORIES:
        keys = [key for key, scene in SCENES.items() if category in scene.events]
        if category not in PRIMARY_EVENTS:
            keys = [category]
        if not keys:
            keys = ["event_star_alignment", "event_portal"] if category == "midnight" else ["event_fireworks"]
        lunar = category in {"moonrise", "moonset", "full_moon", "new_moon"}
        panels = ["time"] if category in PRIMARY_EVENTS else (
            ["time", "phase", "illumination", "next_event", "next_full"] if lunar else
            ["time", "day_length", "day_delta", "next_event", "twilight"])
        result[category] = Event(
            enabled=category in DEFAULT_ENABLED_EVENTS, scenes=keys,
            duration_seconds={"hour":10, "half":8, "quarter":6, "midnight":12}.get(category,45),
            panels=panels,
        )
    return result


class Sleep(StrictModel):
    enabled: bool = True
    start: str = Field(default="02:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(default="08:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    brightness: int = Field(default=1, ge=0, le=255)
    color: Color = "#ff500c"
    mode: Literal["auto", "sleep", "wake"] = "auto"
    until: datetime | None = None

    @model_validator(mode="after")
    def validate_sleep(self):
        if self.start == self.end:
            raise ValueError("Sleep start and end must differ")
        if self.until is not None and (self.until.tzinfo is None or self.until.utcoffset() is None):
            raise ValueError("Sleep override expiry must have a timezone")
        return self


class Location(StrictModel):
    source: Literal["weather", "custom"] = "weather"
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_location(self):
        if self.source == "custom" and (self.latitude is None or self.longitude is None):
            raise ValueError("Custom location requires latitude and longitude")
        return self


class Config(StrictModel):
    version: Literal[1] = 1
    enabled: bool = True
    timezone: str = "Europe/Vienna"
    after_entries: int = Field(default=2, ge=0, le=100)
    interval_seconds: int = Field(default=50, ge=0, le=3600)
    duration_seconds: int = Field(default=8, ge=1, le=300)
    selection: Literal["ordered", "random"] = "ordered"
    avoid_style_repeat: bool = True
    scenes: list[str] = Field(default_factory=_normal_keys, min_length=1, max_length=64)
    weights: dict[str, Annotated[int, Field(ge=1, le=10)]] = Field(default_factory=dict)
    profile: Literal["all", "retro", "calm", "favorites", "custom"] = "all"
    favorites: list[str] = Field(default_factory=list, max_length=64)
    intensity: Literal["calm", "normal", "lively"] = "normal"
    color: Color | None = None
    minute_transition: bool = True
    event_grace_seconds: int = Field(default=120, ge=0, le=3600)
    events: dict[str, Event] = Field(default_factory=_default_events)
    sleep: Sleep = Field(default_factory=Sleep)
    location: Location = Field(default_factory=Location)
    profiles: dict[str, dict] = Field(default_factory=dict)

    @field_validator("profiles")
    @classmethod
    def valid_profiles(cls, value):
        if len(value) > 8 or any(not isinstance(name, str) or not 1 <= len(name.strip()) <= 40 or name.strip() in {"__proto__", "constructor", "prototype"} for name in value) or len({name.strip() for name in value}) != len(value):
            raise ValueError("Up to eight named profiles with 1–40 character names")
        # Profiles contain only scene preferences, not schedules or sleep overrides.
        fields = {"scenes", "favorites", "weights", "selection", "avoid_style_repeat", "intensity", "color"}
        normalized = {}
        for name, profile in value.items():
            if not isinstance(profile, dict) or set(profile) - fields:
                raise ValueError("Invalid scene profile")
            candidate = cls.model_validate({**profile, "profiles": {}}).model_dump(mode="json")
            normalized[name.strip()] = {field: candidate[field] for field in fields}
        return normalized

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown timezone") from exc
        return value

    @field_validator("scenes", "favorites")
    @classmethod
    def valid_normal_scenes(cls, value):
        allowed = set(_normal_keys())
        if len(value) != len(set(value)) or any(key not in allowed for key in value):
            raise ValueError("Unknown or duplicate normal scene")
        return value

    @field_validator("weights")
    @classmethod
    def valid_weights(cls, value):
        if any(key not in _normal_keys() for key in value):
            raise ValueError("Unknown weighted scene")
        return value

    @field_validator("events")
    @classmethod
    def valid_events(cls, value):
        if any(key not in EVENT_CATEGORIES for key in value):
            raise ValueError("Unknown event category")
        merged = {**_default_events(), **value}
        from app.services.time_stage import EVENT_SCENES
        milestone_keys = {scene.key for scene in EVENT_SCENES}
        for category, event in merged.items():
            allowed = milestone_keys if category in PRIMARY_EVENTS else {category}
            if any(key not in allowed for key in event.scenes):
                raise ValueError("Scene does not match event category")
            if category not in PRIMARY_EVENTS and event.duration_seconds < 30:
                raise ValueError("Celestial ceremonies require 30–60 seconds")
        return merged


TimeStageConfig = Config


async def save_config(db, config):
    """Stage a preference update; the caller owns the transaction and lock."""
    value = Config.model_validate(config).model_dump(mode="json")
    preference = await db.get(TimeStagePreference, "config")
    if preference is None:
        db.add(TimeStagePreference(key="config", value=value))
    else:
        preference.value = value
    return value


LEGACY_SCENES = {
    "classic": "retro_cartridge", "arcade": "retro_platformer",
    "progress": "chroma_prism", "binary": "craft_binary_precision",
    "orbit": "cyber_orbit", "neon": "chroma_neon_pulse", "flip": "craft_mechanical_flip",
}


async def load_or_migrate(db, system_settings) -> dict:
    preference = await db.get(TimeStagePreference, "config")
    if preference is not None:
        # Invalid/newer versions must be surfaced, never replaced with defaults.
        return Config.model_validate(preference.value).model_dump(mode="json")

    rows = list((await db.scalars(select(ModuleConfig).order_by(ModuleConfig.sort_order, ModuleConfig.id))).all())
    clocks = [row for row in rows if row.key.split("-", 1)[0].split(":", 1)[0] == "clock" or (row.settings or {}).get("kind") == "clock"]
    config = Config(timezone=getattr(system_settings, "tz", "Europe/Vienna")).model_dump(mode="json")
    if clocks:
        archive = [{column.name: deepcopy(getattr(row, column.name)) for column in ModuleConfig.__table__.columns} for row in clocks]
        if await db.get(TimeStagePreference, "legacy_clocks") is None:
            db.add(TimeStagePreference(key="legacy_clocks", value=archive))
        enabled = next((row for row in clocks if row.enabled), None)
        config["enabled"] = enabled is not None
        if enabled is not None:
            old = enabled.settings or {}
            config["timezone"] = old.get("timezone", config["timezone"])
            config["duration_seconds"] = enabled.duration_seconds
            config["interval_seconds"] = old.get("priority_every", 50)
            # Legacy colors remain in the archive; new artistic scenes use their
            # own palettes unless an explicit global color override is enabled.
            mapped = []
            for key in old.get("variants", []):
                candidate = key if key in _normal_keys() else LEGACY_SCENES.get(key)
                if candidate in _normal_keys() and candidate not in mapped:
                    mapped.append(candidate)
            if mapped:
                config["scenes"] = mapped + [key for key in _normal_keys() if key not in mapped]
        # Validate before modifying any legacy rows.
        config = Config.model_validate(config).model_dump(mode="json")
        for row in clocks:
            row.enabled = False
    config = await save_config(db, config)
    await db.commit()
    return config
