import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from app.services.led_driver import SerialException

from app.api.deps import get_current_user
from app.database import get_db
from app.models import DisplayPreference
from app.schemas import BrightnessRequest, DrawRequest, ManualTextRequest

router = APIRouter(prefix="/api/display", tags=["display"])


def _display(request: Request):
    service = getattr(request.app.state, "display_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="display service unavailable")
    return service


@router.post("/text")
async def show_text(payload: ManualTextRequest, request: Request, _: str = Depends(get_current_user)):
    _display(request).set_manual_text(
        payload.text,
        payload.seconds,
        payload.font_size,
        payload.color,
        payload.x_offset,
        payload.y_offset,
    )
    return {"ok": True}


@router.post("/draw")
async def draw(payload: DrawRequest, request: Request, _: str = Depends(get_current_user)):
    if len(payload.pixels) != 8 or any(len(row) != 32 for row in payload.pixels):
        raise HTTPException(status_code=400, detail="pixels must be 8x32")
    _display(request).set_manual_pixels(payload.pixels, payload.seconds)
    return {"ok": True}


@router.post("/brightness")
async def brightness(payload: BrightnessRequest, request: Request, _: str = Depends(get_current_user), db=Depends(get_db)):
    service = _display(request)
    async with service.brightness_lock:
        preference = await db.get(DisplayPreference, "brightness")
        if preference is None:
            db.add(DisplayPreference(key="brightness", value=payload.brightness))
        else:
            preference.value = payload.brightness
        await db.commit()
        try:
            await asyncio.to_thread(service.set_brightness, payload.brightness)
        except (SerialException, OSError) as exc:
            raise HTTPException(status_code=503, detail="Helligkeit gespeichert; Uno derzeit nicht erreichbar. Wird bei Wiederverbindung angewendet.") from exc
    return {"ok": True}


@router.get("/brightness")
async def get_brightness(request: Request, _: str = Depends(get_current_user), db=Depends(get_db)):
    preference = await db.get(DisplayPreference, "brightness")
    snapshot = _display(request).led_driver.get_debug_snapshot(poll=False)
    return {"brightness": preference.value if preference is not None else snapshot["brightness"],
            "effective_brightness": snapshot["brightness"],
            "persisted": preference is not None,
            "connected": snapshot.get("serial", {}).get("connected", True)}


@router.delete("/manual/clear")
async def clear_manual_override(request: Request, _: str = Depends(get_current_user)):
    _display(request).clear_manual_override()
    return {"ok": True}
