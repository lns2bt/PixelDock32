from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_current_user
from app.schemas_debug import DebugPatternRequest, GpioInputProbeRequest, GpioOutputTestRequest

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


def _external(request: Request):
    external = getattr(request.app.state, "external_data_service", None)
    if external is None:
        raise HTTPException(status_code=503, detail="external data service unavailable")
    return external


@router.get("/status")
async def status(request: Request, _: str = Depends(get_current_user)):
    display_service = _display(request)
    external = getattr(request.app.state, "external_data_service", None)
    cache = external.cache if external else {}
    live_data = display_service.get_live_data_snapshot()
    poll_state = {
        "external_running": bool(getattr(external, "_running", False)),
        "poll_task_count": len(getattr(external, "_tasks", []) or []),
        "dht_enabled": bool(getattr(getattr(external, "settings", None), "dht_enabled", False)),
        "poll_intervals": {
            "btc_seconds": getattr(getattr(external, "settings", None), "poll_btc_seconds", None),
            "weather_seconds": getattr(getattr(external, "settings", None), "poll_weather_seconds", None),
            "dht_seconds": getattr(getattr(external, "settings", None), "poll_dht_seconds", None),
        },
    }
    return {
        "display": display_service.get_status(),
        "live_data": live_data,
        "live_data_debug": {
            "source": "display_cache_snapshot",
            "snapshot_ts": display_service.last_cache_snapshot_ts,
            "has_any_values": any(value is not None for value in live_data.values()),
            "external_cache_keys": sorted(list(cache.keys())),
            "display_cache_keys": sorted(list(display_service.last_cache_snapshot.keys())),
            "poll_state": poll_state,
            "errors": {
                "btc_error": cache.get("btc_error"),
                "weather_error": cache.get("weather_error"),
                "dht_error": cache.get("dht_error"),
                "btc_block_height_error": cache.get("btc_block_height_error"),
            },
            "timestamps": {
                "btc_updated_at": cache.get("btc_updated_at"),
                "btc_block_height_updated_at": cache.get("btc_block_height_updated_at"),
                "weather_updated_at": cache.get("weather_updated_at"),
                "dht_updated_at": cache.get("dht_updated_at"),
                "dht_last_attempt_at": cache.get("dht_last_attempt_at"),
                "display_last_frame_ts": display_service.last_frame_ts,
            },
        },
        "data": {
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
            "dht_last_success_source": cache.get("dht_last_success_source"),
            "dht_last_error_source": cache.get("dht_last_error_source"),
            "dht_source_stats": cache.get("dht_source_stats"),
            "dht_backend_stats": cache.get("dht_backend_stats"),
            "dht_diagnostics": cache.get("dht_diagnostics"),
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
    x: int,
    y: int,
    _: str = Depends(get_current_user),
):
    if x < 0 or x > 31 or y < 0 or y > 7:
        raise HTTPException(status_code=422, detail="x/y out of range")
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
            "backend": cache.get("dht_backend"),
            "last_success_source": cache.get("dht_last_success_source"),
            "last_error_source": cache.get("dht_last_error_source"),
        },
        "attempts": {
            "source_stats": cache.get("dht_source_stats"),
            "backend_stats": cache.get("dht_backend_stats"),
            "disabled_backends": cache.get("dht_disabled_backends"),
            "trace": cache.get("dht_trace"),
        },
        "diagnostics": cache.get("dht_diagnostics"),
        "processing": cache.get("dht_processing"),
        "derived_cache": {
            "weather_indoor_temp": cache.get("weather_indoor_temp"),
            "weather_indoor_humidity": cache.get("weather_indoor_humidity"),
            "weather_outdoor_temp": cache.get("weather_outdoor_temp"),
            "weather_source": cache.get("weather_source"),
        },
    }



@router.post("/dht/read-once")
async def dht_read_once(request: Request, _: str = Depends(get_current_user)):
    external = _external(request)
    result = external.read_dht_debug_snapshot()
    return {"ok": True, "result": result}


@router.get("/gpio/environment")
async def gpio_environment(request: Request, _: str = Depends(get_current_user)):
    result = _external(request).get_gpio_environment_report()
    return {"ok": True, "result": result}

@router.post("/gpio/output-test")
async def gpio_output_test(payload: GpioOutputTestRequest, request: Request, _: str = Depends(get_current_user)):
    result = _external(request).run_gpio_output_test(
        gpio_pin=payload.gpio_pin,
        pulses=payload.pulses,
        hold_ms=payload.hold_ms,
    )
    return {"ok": True, "result": result}


@router.post("/gpio/input-probe")
async def gpio_input_probe(payload: GpioInputProbeRequest, request: Request, _: str = Depends(get_current_user)):
    result = _external(request).run_gpio_input_probe(
        gpio_pin=payload.gpio_pin,
        sample_ms=payload.sample_ms,
        pull_up=payload.pull_up,
    )
    return {"ok": True, "result": result}
