import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field
from pydantic import ValidationError
from PIL import Image
from sqlalchemy import select

from app.api.deps import get_current_user
from app.database import get_db
from app.models import ModuleConfig
from app.services.assets import MAX_UPLOAD, MAX_FRAMES, MAX_ASSET_BYTES, decode_image, analyze_image

router = APIRouter(prefix="/api/assets", tags=["assets"])
decode_slot = asyncio.Semaphore(1)


class SpriteRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    frames: list[dict] = Field(min_length=1, max_length=MAX_FRAMES)


def store(request):
    return request.app.state.asset_store


@router.get("")
async def list_assets(request: Request, _: str = Depends(get_current_user)):
    return await asyncio.to_thread(store(request).list)


@router.post("/import", status_code=201)
async def import_image(request: Request, name: str = Query(default="Import", min_length=1, max_length=80),
                       fit: str = Query(default="contain", pattern="^(contain|cover|stretch)$"),
                       trim_start: int = Query(default=0, ge=0, le=4096),
                       trim_end: int = Query(default=0, ge=0, le=4096),
                       step: int = Query(default=1, ge=1, le=64),
                       range_kind: str = Query(default='frames', pattern='^(frames|time)$'),
                       start_seconds: float = Query(default=0, ge=0, allow_inf_nan=False),
                       end_seconds: float | None = Query(default=None, gt=0, allow_inf_nan=False),
                       preview: bool = False,
                       _: str = Depends(get_current_user)):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_UPLOAD:
            raise HTTPException(413, "Maximal 4 MB")
    try:
        async with decode_slot:
            data = await asyncio.to_thread(decode_image, bytes(raw), name, fit,
                                         trim_start=trim_start, trim_end=trim_end, step=step,
                                         range_kind=range_kind, start_seconds=start_seconds, end_seconds=end_seconds)
        if preview:
            return {**data, 'cycle_seconds':sum(f['duration_ms'] for f in data['frames'])/1000}
        return await asyncio.to_thread(store(request).save, data)
    except (ValueError, OSError, Warning, Image.DecompressionBombError) as error:
        raise HTTPException(422, str(error)) from error


@router.post('/analyze')
async def analyze(request: Request, _: str = Depends(get_current_user)):
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>MAX_UPLOAD: raise HTTPException(413,'Maximal 4 MB')
    try:
        async with decode_slot:
            return await asyncio.to_thread(analyze_image,bytes(raw))
    except (ValueError,OSError,Warning,Image.DecompressionBombError) as error:
        raise HTTPException(422,str(error)) from error


@router.post("/sprites", status_code=201)
async def create_sprite(request: Request, _: str = Depends(get_current_user)):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_ASSET_BYTES:
            raise HTTPException(413, "Sprite-Datei zu groß: maximal 2 MB")
    try:
        payload = SpriteRequest.model_validate(json.loads(raw))
        return await asyncio.to_thread(store(request).save, payload.model_dump())
    except (ValueError, ValidationError) as error:
        raise HTTPException(422, f"Ungültige Sprite-Daten: Name, 1–{MAX_FRAMES} Frames, je 256 RGB-Pixel und 33–2000 ms erforderlich") from error


@router.get("/{asset_id}")
async def get_asset(asset_id: str, request: Request, _: str = Depends(get_current_user)):
    try:
        return await asyncio.to_thread(store(request).load, asset_id)
    except (ValueError, OSError) as error:
        raise HTTPException(404, "Asset nicht gefunden") from error


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str, request: Request, _: str = Depends(get_current_user), db=Depends(get_db)):
    rows = (await db.execute(select(ModuleConfig))).scalars().all()
    if any((row.settings or {}).get("asset_id") == asset_id for row in rows):
        raise HTTPException(409, "Asset wird noch in einem Modul verwendet")
    if asset_id.startswith("demo_"):
        raise HTTPException(409, "Beispiel-Assets bleiben in der Bibliothek")
    try:
        await asyncio.to_thread(store(request).delete, asset_id)
    except (ValueError, OSError) as error:
        raise HTTPException(404, "Asset nicht gefunden") from error
    return {"ok": True}
