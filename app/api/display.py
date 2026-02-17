from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_current_user
from app.schemas import BrightnessRequest, DrawRequest, ManualTextRequest

router = APIRouter(prefix="/api/display", tags=["display"])


def _display(request: Request):
    service = getattr(request.app.state, "display_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="display service unavailable")
    return service


@router.post("/text")
async def show_text(payload: ManualTextRequest, request: Request, _: str = Depends(get_current_user)):
    _display(request).set_manual_text(payload.text, payload.seconds)
    return {"ok": True}


@router.post("/draw")
async def draw(payload: DrawRequest, request: Request, _: str = Depends(get_current_user)):
    if len(payload.pixels) != 8 or any(len(row) != 32 for row in payload.pixels):
        raise HTTPException(status_code=400, detail="pixels must be 8x32")
    _display(request).set_manual_pixels(payload.pixels, payload.seconds)
    return {"ok": True}


@router.post("/brightness")
async def brightness(payload: BrightnessRequest, request: Request, _: str = Depends(get_current_user)):
    _display(request).set_brightness(payload.brightness)
    return {"ok": True}
