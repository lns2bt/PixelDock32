"""Authenticated, hardware-passive preference and preview endpoints."""

import inspect
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from pydantic import Field, field_validator
from typing import Literal

from app.api.deps import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import TimeStagePreference
from app.services.time_stage import catalog
from app.services.time_stage.settings import Config, StrictModel, save_config

router = APIRouter(prefix="/api/time-stage", tags=["time-stage"], dependencies=[Depends(get_current_user)])


class ImportRequest(StrictModel):
    version: Literal[1]
    config: Config


class SleepRequest(StrictModel):
    mode: Literal["auto", "sleep", "wake"]
    minutes: int | None = Field(default=None, ge=1, le=1440)


class PreviewRequest(StrictModel):
    key: str
    at: datetime | None = None
    elapsed: float = Field(default=0, ge=0, le=120, allow_inf_nan=False)
    physical: bool = False
    confirm_wake: bool = False

    @field_validator("key")
    @classmethod
    def valid_key(cls, value):
        from app.services.time_stage import SCENES
        from app.services.time_stage.celestial import KEYS
        if value not in SCENES and value not in KEYS:
            raise ValueError("Unknown scene")
        return value


def _display(request):
    service = getattr(request.app.state, "display_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="display service unavailable")
    return service


async def _config(db, service):
    preference = await db.get(TimeStagePreference, "config")
    value = preference.value if preference is not None else getattr(service, "time_stage_config", None)
    return Config.model_validate(value or {}).model_dump(mode="json")


def _location(config, service):
    location = deepcopy(config["location"])
    if location["source"] == "weather":
        settings = get_settings()
        location.update(latitude=settings.weather_lat, longitude=settings.weather_lon)
    return location


def _snapshot(config, service):
    from app.services.time_stage.celestial import KEYS, PANELS
    scenes = catalog()
    for scene in scenes:
        if scene['events'] and 'midnight' not in scene['events']:
            scene['events'].append('midnight')
    scenes += [
        {"key": key, "title": key.replace("_", " ").title(), "style": "Celestial",
         "description": "Astronomical ceremony with local facts", "seconds": "Wall-clock time",
         "duration": 45, "events": [key], "panels": list(PANELS)} for key in KEYS
    ]
    return {"config": config, "catalog": scenes, "status": service.time_stage_status(),
            "astronomy": getattr(service, "astronomy_data", {}) or {},
            "location": _location(config, service)}


async def _save(db, service, config):
    async with service.brightness_lock:
        value = await save_config(db, config)
        await db.commit()
        service.configure_time_stage(value)
    return value


@router.get("")
async def get_time_stage(request: Request, db=Depends(get_db)):
    service = _display(request)
    return _snapshot(await _config(db, service), service)


@router.put("")
async def put_time_stage(payload: Config, request: Request, db=Depends(get_db)):
    service = _display(request)
    config = await _save(db, service, payload.model_dump(mode="json"))
    return _snapshot(config, service)


@router.get("/export")
async def export_time_stage(request: Request, db=Depends(get_db)):
    config = await _config(db, _display(request))
    config["sleep"].update(mode="auto", until=None)
    return {"version": 1, "config": config}


@router.post("/import")
async def import_time_stage(payload: ImportRequest, request: Request, db=Depends(get_db)):
    service = _display(request)
    config = await _save(db, service, payload.config.model_dump(mode="json"))
    return _snapshot(config, service)


@router.post("/sleep")
async def set_sleep(payload: SleepRequest, request: Request, db=Depends(get_db)):
    service = _display(request)
    # Read-modify-write under the same lock as ordinary preference writes.
    async with service.brightness_lock:
        config = await _config(db, service)
        now = datetime.now(ZoneInfo(config["timezone"]))
        until = None
        if payload.mode != "auto":
            if payload.minutes is not None:
                until = (now.astimezone(timezone.utc) + timedelta(minutes=payload.minutes)).astimezone(now.tzinfo)
            else:
                from app.services.time_stage.engine import next_sleep_boundary
                until = next_sleep_boundary(now, config)
        config["sleep"].update(mode=payload.mode, until=until.isoformat() if until else None)
        config = await save_config(db, config)
        await db.commit()
        service.configure_time_stage(config)
    return service.time_stage_status()


@router.post("/preview")
async def preview(payload: PreviewRequest, request: Request, db=Depends(get_db)):
    service = _display(request)
    if payload.physical:
        status = service.time_stage_status()
        if (status.get("sleep_active") or status.get("sleeping") or
                status.get("sleep", {}).get("active")) and not payload.confirm_wake:
            raise HTTPException(status_code=409, detail="Sleep is active; confirm_wake is required")
        try:
            result = service.preview_time_stage(payload.key, confirm_wake=payload.confirm_wake)
            if inspect.isawaitable(result):
                result = await result
        except (ValueError, PermissionError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return jsonable_encoder(result if result is not None else {"ok": True})
    config = await _config(db, service)
    timezone = ZoneInfo(config["timezone"])
    now = payload.at or datetime.now(timezone)
    now = now.replace(tzinfo=timezone) if now.tzinfo is None else now.astimezone(timezone)
    renderer = getattr(service, "preview_for_browser", service.render_time_stage_preview)
    result = await asyncio.to_thread(renderer, payload.key, now, payload.elapsed)
    if inspect.isawaitable(result):
        result = await result
    encoded = jsonable_encoder(result)
    colors = encoded.get("color_frame")
    if colors is not None:
        encoded["pixels"] = [
            (color[0] << 16) | (color[1] << 8) | color[2] if color else 0
            for row in colors for color in row
        ]
    else:
        color = encoded.get("default_color", [80, 80, 80])
        packed = (color[0] << 16) | (color[1] << 8) | color[2]
        encoded["pixels"] = [packed if pixel else 0 for row in encoded.get("frame", []) for pixel in row]
    encoded.update(key=payload.key, at=now.isoformat(), elapsed=payload.elapsed)
    return encoded
