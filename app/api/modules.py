from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models import ModuleConfig
from app.schemas import ModuleConfigResponse, ModuleConfigUpdate
from app.services.module_manager import list_modules

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
        "color_cold": "#3b82f6",
        "color_warm": "#f97316",
        "color_fallback": "#9ca3af",
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
}


ALLOWED_FONT_SIZES = {"small", "normal"}
ALLOWED_TRANSITIONS = {"down", "up"}
ALLOWED_TEXT_MODES = {"static", "scroll"}
ALLOWED_TEXTBOX_PRESETS = {"welcome", "status", "alert", "ticker"}


def _clamp_int(value: object, minimum: int, maximum: int, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, parsed))


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


def sanitize_settings(module_key: str, settings: dict) -> dict:
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
        merged["color_cold"] = _normalize_hex_color(merged.get("color_cold"), defaults["color_cold"])
        merged["color_warm"] = _normalize_hex_color(merged.get("color_warm"), defaults["color_warm"])
        merged["color_fallback"] = _normalize_hex_color(merged.get("color_fallback"), defaults["color_fallback"])
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

    return merged


@router.get("", response_model=list[ModuleConfigResponse])
async def get_modules(_: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await list_modules(db)


@router.put("/{module_id}", response_model=ModuleConfigResponse)
async def update_module(
    module_id: int,
    payload: ModuleConfigUpdate,
    _: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    module = await db.get(ModuleConfig, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="module not found")

    module.enabled = payload.enabled
    module.duration_seconds = payload.duration_seconds
    module.sort_order = payload.sort_order
    module.settings = sanitize_settings(module.key, payload.settings)

    await db.commit()
    await db.refresh(module)
    return module
