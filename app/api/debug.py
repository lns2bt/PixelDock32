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
            "weather_updated_at": cache.get("weather_updated_at"),
            "weather_error": cache.get("weather_error"),
        },
    }


@router.get("/preview")
async def preview(request: Request, _: str = Depends(get_current_user)):
    frame = _display(request).get_preview_frame()
    lit_pixels = sum(sum(1 for px in row if px) for row in frame)
    return {"width": 32, "height": 8, "lit_pixels": lit_pixels, "frame": frame}


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
