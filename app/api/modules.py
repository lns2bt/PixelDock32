import asyncio
import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models import ModuleConfig
from app.schemas import ModuleConfigResponse, ModuleConfigUpdate, ModuleCreate, ModuleOrder
from app.services.module_manager import list_modules
from app.services.module_visuals import CLOCK_VARIANTS, DEFAULT_CLOCK_VARIANTS

router = APIRouter(prefix="/api/modules", tags=["modules"])


MODULE_SETTING_DEFAULTS = {
    "clock": {
        "timezone": "Europe/Vienna",
        "show_seconds": True,
        "font_size": "normal",
        "color": "#c8e6ff",
        "x_offset": 0,
        "y_offset": 0,
        "transition_direction": "down",
        "transition_ms": 350,
    },
    "btc": {
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
    "weather": {
        "postcode": "6020",
        "font_size": "normal",
        "x_offset": 0,
        "y_offset": 0,
        "char_spacing": 1,
        "color_cold": "#3b82f6",
        "color_warm": "#f97316",
        "color_humidity": "#6ed2ff",
        "color_fallback": "#9ca3af",
        "screen_seconds": 4,
        "transition_direction": "down",
        "transition_ms": 350,
    },
    "textbox": {
        "lines": "HELLO\nPIXELDOCK",
        "line_seconds": 2,
        "font_size": "small",
        "color": "#f4f4f5",
        "x_offset": 0,
        "y_offset": 0,
        "transition_direction": "down",
        "transition_ms": 450,
        "text_mode": "static",
        "scroll_speed": 35,
        "preset": "welcome",
    },
    "animations": {
        "preset": "bit_invaders",
        "speed": 1.0,
        "palette": "neon",
        "intensity": 0.8,
        "mirror_mode": "none",
        "transition_direction": "down",
        "transition_ms": 450,
    },
    "bitmap": {
        "file": "sample_gradient.ppm", "scroll_direction": "top_to_bottom",
        "scroll_speed": 2.0, "color_mode": "bitmap", "transition_ms": 350,
    },
}


ALLOWED_FONT_SIZES = {"small", "normal"}
ALLOWED_TRANSITIONS = {"down", "up"}
ALLOWED_TEXT_MODES = {"static", "scroll"}
ALLOWED_TEXTBOX_PRESETS = {"welcome", "status", "alert", "ticker"}
ALLOWED_ANIMATION_PRESETS = {
    "psychedelic_plasma",
    "retro_rainbow_tunnel",
    "bit_invaders",
    "neon_equalizer",
    "matrix_rain",
    "lava_lamp",
    "pixel_snake",
}
ALLOWED_ANIMATION_PALETTES = {"neon", "rainbow", "fire", "ocean", "matrix"}
ALLOWED_MIRROR_MODES = {"none", "horizontal", "vertical", "quad"}


def _clamp_int(value: object, minimum: int, maximum: int, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, parsed))


def _clamp_float(value: object, minimum: float, maximum: float, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, parsed)) if math.isfinite(parsed) else fallback


def _normalize_font_size(value: object, fallback: str = "normal") -> str:
    if isinstance(value, str) and value.lower() in ALLOWED_FONT_SIZES:
        return value.lower()
    return fallback


def _normalize_hex_color(value: object, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    v = value.strip()
    if not v:
        return fallback
    if not v.startswith("#"):
        v = f"#{v}"
    if len(v) != 7:
        return fallback
    hex_part = v[1:]
    if any(c not in "0123456789abcdefABCDEF" for c in hex_part):
        return fallback
    return v.lower()


def _normalize_transition_direction(value: object, fallback: str = "down") -> str:
    if isinstance(value, str) and value.lower() in ALLOWED_TRANSITIONS:
        return value.lower()
    return fallback


def _normalize_text_mode(value: object, fallback: str = "static") -> str:
    if isinstance(value, str) and value.lower() in ALLOWED_TEXT_MODES:
        return value.lower()
    return fallback


def _normalize_textbox_preset(value: object, fallback: str = "welcome") -> str:
    if isinstance(value, str) and value.lower() in ALLOWED_TEXTBOX_PRESETS:
        return value.lower()
    return fallback


def _normalize_allowed_string(value: object, allowed: set[str], fallback: str) -> str:
    if isinstance(value, str) and value.strip().lower() in allowed:
        return value.strip().lower()
    return fallback


def sanitize_settings(module_key: str, settings: dict) -> dict:
    module_key = module_key.split("-")[0]
    defaults = MODULE_SETTING_DEFAULTS.get(module_key, {})
    merged = {**defaults, **(settings or {})}

    if module_key == "clock":
        merged["timezone"] = str(merged.get("timezone", defaults["timezone"])).strip() or defaults["timezone"]
        merged["show_seconds"] = bool(merged.get("show_seconds", defaults["show_seconds"]))
        merged["font_size"] = _normalize_font_size(merged.get("font_size"), defaults["font_size"])
        merged["color"] = _normalize_hex_color(merged.get("color"), defaults["color"])
        merged["x_offset"] = _clamp_int(merged.get("x_offset"), -16, 16, defaults["x_offset"])
        merged["y_offset"] = _clamp_int(merged.get("y_offset"), -4, 4, defaults["y_offset"])
        merged["transition_direction"] = _normalize_transition_direction(
            merged.get("transition_direction"), defaults["transition_direction"]
        )
        merged["transition_ms"] = _clamp_int(merged.get("transition_ms"), 0, 2000, defaults["transition_ms"])

    elif module_key == "btc":
        from app.services.bitcoin_stage import normalize
        merged = normalize(merged)
        merged.pop("_bitcoin_preview", None)
        merged["font_size"] = _normalize_font_size(merged.get("font_size"), defaults["font_size"])
        merged["x_offset"] = _clamp_int(merged.get("x_offset"), -16, 16, defaults["x_offset"])
        merged["y_offset"] = _clamp_int(merged.get("y_offset"), -4, 4, defaults["y_offset"])
        merged["color_b"] = _normalize_hex_color(merged.get("color_b"), defaults["color_b"])
        merged["color_up"] = _normalize_hex_color(merged.get("color_up"), defaults["color_up"])
        merged["color_down"] = _normalize_hex_color(merged.get("color_down"), defaults["color_down"])
        merged["color_flat"] = _normalize_hex_color(merged.get("color_flat"), defaults["color_flat"])
        merged["color_fallback"] = _normalize_hex_color(merged.get("color_fallback"), defaults["color_fallback"])
        merged["transition_direction"] = _normalize_transition_direction(
            merged.get("transition_direction"), defaults["transition_direction"]
        )
        merged["transition_ms"] = _clamp_int(merged.get("transition_ms"), 0, 2000, defaults["transition_ms"])

    elif module_key == "weather":
        merged["postcode"] = str(merged.get("postcode", defaults["postcode"])).strip() or defaults["postcode"]
        merged["font_size"] = _normalize_font_size(merged.get("font_size"), defaults["font_size"])
        merged["x_offset"] = _clamp_int(merged.get("x_offset"), -16, 16, defaults["x_offset"])
        merged["y_offset"] = _clamp_int(merged.get("y_offset"), -4, 4, defaults["y_offset"])
        merged["char_spacing"] = _clamp_int(merged.get("char_spacing"), 0, 4, defaults["char_spacing"])
        merged["color_cold"] = _normalize_hex_color(merged.get("color_cold"), defaults["color_cold"])
        merged["color_warm"] = _normalize_hex_color(merged.get("color_warm"), defaults["color_warm"])
        merged["color_humidity"] = _normalize_hex_color(merged.get("color_humidity"), defaults["color_humidity"])
        merged["color_fallback"] = _normalize_hex_color(merged.get("color_fallback"), defaults["color_fallback"])
        merged["screen_seconds"] = _clamp_int(merged.get("screen_seconds"), 1, 60, defaults["screen_seconds"])
        merged["transition_direction"] = _normalize_transition_direction(
            merged.get("transition_direction"), defaults["transition_direction"]
        )
        merged["transition_ms"] = _clamp_int(merged.get("transition_ms"), 0, 2000, defaults["transition_ms"])

    elif module_key == "textbox":
        merged["lines"] = str(merged.get("lines", defaults["lines"]))
        merged["line_seconds"] = _clamp_int(merged.get("line_seconds"), 1, 30, defaults["line_seconds"])
        merged["font_size"] = _normalize_font_size(merged.get("font_size"), defaults["font_size"])
        merged["color"] = _normalize_hex_color(merged.get("color"), defaults["color"])
        merged["x_offset"] = _clamp_int(merged.get("x_offset"), -16, 16, defaults["x_offset"])
        merged["y_offset"] = _clamp_int(merged.get("y_offset"), -4, 4, defaults["y_offset"])
        merged["transition_direction"] = _normalize_transition_direction(
            merged.get("transition_direction"), defaults["transition_direction"]
        )
        merged["transition_ms"] = _clamp_int(merged.get("transition_ms"), 0, 2000, defaults["transition_ms"])
        merged["text_mode"] = _normalize_text_mode(merged.get("text_mode"), defaults["text_mode"])
        merged["scroll_speed"] = _clamp_int(merged.get("scroll_speed"), 5, 120, defaults["scroll_speed"])
        merged["preset"] = _normalize_textbox_preset(merged.get("preset"), defaults["preset"])

    elif module_key == "animations":
        merged["preset"] = _normalize_allowed_string(
            merged.get("preset"), ALLOWED_ANIMATION_PRESETS, defaults["preset"]
        )
        merged["speed"] = _clamp_float(merged.get("speed"), 0.1, 5.0, defaults["speed"])
        merged["palette"] = _normalize_allowed_string(
            merged.get("palette"), ALLOWED_ANIMATION_PALETTES, defaults["palette"]
        )
        merged["intensity"] = _clamp_float(merged.get("intensity"), 0.1, 1.0, defaults["intensity"])
        merged["mirror_mode"] = _normalize_allowed_string(
            merged.get("mirror_mode"), ALLOWED_MIRROR_MODES, defaults["mirror_mode"]
        )
        merged["transition_direction"] = _normalize_transition_direction(
            merged.get("transition_direction"), defaults["transition_direction"]
        )
        merged["transition_ms"] = _clamp_int(merged.get("transition_ms"), 0, 2000, defaults["transition_ms"])

    merged["kind"] = module_key
    merged["transition_effect"] = _normalize_allowed_string(merged.get("transition_effect"), {"fade", "dissolve", "slide", "none"}, "fade")
    merged["transition_ms"] = _clamp_int(merged.get("transition_ms", 450), 0, 2000, 450)
    merged["transition_on_content_change"] = False
    merged["shuffle"] = bool(merged.get("shuffle", False))
    merged["priority_every"] = _clamp_int(merged.get("priority_every", 45 if module_key == "clock" else 0), 0, 3600, 0)
    merged["speed"] = _clamp_float(merged.get("speed", 1), 0.1, 4, 1)
    if module_key == "clock":
        variants = merged.get("variants", DEFAULT_CLOCK_VARIANTS)
        allowed = CLOCK_VARIANTS
        merged["variants"] = list(dict.fromkeys(v for v in variants if isinstance(v, str) and v in allowed)) if isinstance(variants, list) else []
        if not merged["variants"]:
            merged["variants"] = ["classic"]
        merged.pop("variant_seconds", None)
    if module_key == "weather":
        for key in ("show_outdoor", "show_indoor", "show_humidity"):
            merged[key] = bool(merged.get(key, True))
    return merged


@router.get("", response_model=list[ModuleConfigResponse])
async def get_modules(_: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return [row for row in await list_modules(db) if row.key.split('-')[0] != 'clock']


@router.post("", response_model=ModuleConfigResponse, status_code=201)
async def create_module(payload: ModuleCreate, request: Request, _: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if payload.kind == "clock":
        raise HTTPException(409, "Uhrzeit wird jetzt separat unter Time-Stage eingestellt.")
    if (await db.scalar(select(func.count()).select_from(ModuleConfig))) >= 128:
        raise HTTPException(409, "Maximal 128 Module")
    settings = sanitize_settings(payload.kind, payload.settings)
    if payload.kind == "asset":
        try:
            await asyncio.to_thread(request.app.state.asset_store.load, settings.get("asset_id"))
        except (ValueError, OSError) as error:
            raise HTTPException(422, "Asset nicht gefunden") from error
    order = (await db.scalar(select(func.max(ModuleConfig.sort_order)))) or 0
    module = ModuleConfig(key=payload.kind + "-" + uuid.uuid4().hex[:12], name=payload.name.strip() or payload.kind,
                          enabled=payload.enabled, duration_seconds=payload.duration_seconds, sort_order=order + 1, settings=settings)
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return module


@router.put("/order")
async def reorder_modules(payload: ModuleOrder, _: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = [row for row in await list_modules(db) if row.key.split('-')[0] != 'clock']
    if len(set(payload.ids)) != len(payload.ids) or set(payload.ids) != {row.id for row in rows}:
        raise HTTPException(409, "Modulliste geändert – bitte neu laden")
    order = {module_id: index for index, module_id in enumerate(payload.ids)}
    for row in rows:
        row.sort_order = order[row.id]
    await db.commit()
    return {"ok": True}


@router.post("/{module_id}/play")
async def play_module(module_id: int, request: Request, _: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    module = await db.get(ModuleConfig, module_id)
    if not module:
        raise HTTPException(404, "Modul nicht gefunden")
    if module.key.split('-')[0] == 'clock':
        raise HTTPException(409, "Uhrzeit wird jetzt separat unter Time-Stage eingestellt.")
    service = request.app.state.display_service
    if isinstance(getattr(service, "time_stage_config", None), dict) and service.time_stage.sleep_state(service._stage_now())["active"]:
        raise HTTPException(409, "Schlafmodus aktiv. Bitte zuerst ausdrücklich auf Wach umschalten.")
    request.app.state.display_service.play_once(module)
    return {"ok": True}


@router.delete("/{module_id}")
async def delete_module(module_id: int, _: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    module = await db.get(ModuleConfig, module_id)
    if not module:
        raise HTTPException(404, "Modul nicht gefunden")
    if "-" not in module.key:
        raise HTTPException(409, "Standardmodule bitte deaktivieren statt löschen")
    await db.delete(module)
    await db.commit()
    return {"ok": True}


@router.put("/{module_id}", response_model=ModuleConfigResponse)
async def update_module(
    module_id: int,
    payload: ModuleConfigUpdate,
    request: Request,
    _: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    module = await db.get(ModuleConfig, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="module not found")
    if module.key.split('-')[0] == 'clock':
        raise HTTPException(409, "Archivierte Uhr-Einträge werden durch Time-Stage ersetzt.")

    module.enabled = payload.enabled
    module.duration_seconds = payload.duration_seconds
    module.sort_order = payload.sort_order
    module.settings = sanitize_settings(module.key, payload.settings)
    if module.key.split("-")[0] == "asset":
        try:
            await asyncio.to_thread(request.app.state.asset_store.load, module.settings.get("asset_id"))
        except (ValueError, OSError) as error:
            raise HTTPException(422, "Asset nicht gefunden") from error
    if payload.name is not None:
        module.name = payload.name.strip() or module.name

    await db.commit()
    await db.refresh(module)
    return module
