from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.deps import get_current_user
from app.schemas_debug import DebugPatternRequest

router = APIRouter(prefix="/api/debug", tags=["debug"])


def _display(request: Request):
    service = getattr(request.app.state, "display_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="display service unavailable")
    return service


def _mapper(request: Request):
    mapper = getattr(getattr(request.app.state, "display_service", None), "mapper", None)
    if mapper is None:
        raise HTTPException(status_code=503, detail="mapper unavailable")
    return mapper


@router.get("/status")
async def status(request: Request, _: str = Depends(get_current_user)):
    display_service = _display(request)
    external = getattr(request.app.state, "external_data_service", None)
    cache = external.cache if external else {}
    return {
        "display": display_service.get_status(),
        "data": {
            "btc_eur": cache.get("btc_eur"),
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
        },
    }


@router.get("/preview")
async def preview(request: Request, _: str = Depends(get_current_user)):
    frame = _display(request).get_preview_frame()
    lit_pixels = sum(sum(1 for px in row if px) for row in frame)
    colors = _display(request).get_preview_colors()
    return {"width": 32, "height": 8, "lit_pixels": lit_pixels, "frame": frame, "colors": colors}


@router.get("/mapping/coordinate")
async def explain_coordinate(
    request: Request,
    x: int = Query(ge=0, le=31),
    y: int = Query(ge=0, le=7),
    _: str = Depends(get_current_user),
):
    components = _mapper(request).map_components(x, y)
    return {"ok": True, "mapping": components}


@router.post("/pattern")
async def start_pattern(payload: DebugPatternRequest, request: Request, _: str = Depends(get_current_user)):
    _display(request).set_debug_pattern(payload.pattern, payload.seconds, payload.interval_ms)
    return {"ok": True}


@router.delete("/pattern")
async def stop_pattern(request: Request, _: str = Depends(get_current_user)):
    _display(request).clear_debug_pattern()
    return {"ok": True}


@router.get("/dht")
async def dht_debug(request: Request, _: str = Depends(get_current_user)):
    external = getattr(request.app.state, "external_data_service", None)
    cache = external.cache if external else {}
    return {
        "enabled": bool(getattr(getattr(external, "settings", None), "dht_enabled", False)),
        "gpio_pin": getattr(getattr(external, "settings", None), "dht_gpio_pin", None),
        "model": getattr(getattr(external, "settings", None), "dht_model", None),
        "signal": {
            "gpio_level": cache.get("dht_gpio_level"),
            "last_attempt_at": cache.get("dht_last_attempt_at"),
            "last_duration_ms": cache.get("dht_last_duration_ms"),
            "raw_temperature": cache.get("dht_raw_temperature"),
            "raw_humidity": cache.get("dht_raw_humidity"),
            "last_error": cache.get("dht_error"),
            "last_updated_at": cache.get("dht_updated_at"),
        },
        "processing": cache.get("dht_processing"),
        "derived_cache": {
            "weather_indoor_temp": cache.get("weather_indoor_temp"),
            "weather_indoor_humidity": cache.get("weather_indoor_humidity"),
            "weather_outdoor_temp": cache.get("weather_outdoor_temp"),
            "weather_source": cache.get("weather_source"),
        },
    }
