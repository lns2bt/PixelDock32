from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_current_user
from app.schemas_debug import DebugPatternRequest

router = APIRouter(prefix="/api/debug", tags=["debug"])


def _display(request: Request):
    service = getattr(request.app.state, "display_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="display service unavailable")
    return service


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
            "weather_updated_at": cache.get("weather_updated_at"),
            "weather_error": cache.get("weather_error"),
        },
    }


@router.post("/pattern")
async def start_pattern(payload: DebugPatternRequest, request: Request, _: str = Depends(get_current_user)):
    _display(request).set_debug_pattern(payload.pattern, payload.seconds, payload.interval_ms)
    return {"ok": True}


@router.delete("/pattern")
async def stop_pattern(request: Request, _: str = Depends(get_current_user)):
    _display(request).clear_debug_pattern()
    return {"ok": True}
