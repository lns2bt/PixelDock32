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
from app.services.assets import MAX_UPLOAD, decode_image

router = APIRouter(prefix="/api/assets", tags=["assets"])


class SpriteRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    frames: list[dict] = Field(min_length=1, max_length=120)


def store(request):
    return request.app.state.asset_store


@router.get("")
async def list_assets(request: Request, _: str = Depends(get_current_user)):
    return await asyncio.to_thread(store(request).list)


@router.post("/import", status_code=201)
async def import_image(request: Request, name: str = Query(default="Import", min_length=1, max_length=80),
                       fit: str = Query(default="contain", pattern="^(contain|cover|stretch)$"),
                       _: str = Depends(get_current_user)):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_UPLOAD:
            raise HTTPException(413, "Maximal 4 MB")
    try:
        data = await asyncio.to_thread(decode_image, bytes(raw), name, fit)
        return await asyncio.to_thread(store(request).save, data)
    except (ValueError, OSError, Warning, Image.DecompressionBombError) as error:
        raise HTTPException(422, str(error)) from error


@router.post("/sprites", status_code=201)
async def create_sprite(request: Request, _: str = Depends(get_current_user)):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 512_000:
            raise HTTPException(413, "Sprite-Datei zu groß")
    try:
        payload = SpriteRequest.model_validate(json.loads(raw))
        return await asyncio.to_thread(store(request).save, payload.model_dump())
    except (ValueError, ValidationError) as error:
        raise HTTPException(422, "Ungültige Sprite-Daten: Name, 1–120 Frames, je 256 RGB-Pixel und 33–2000 ms erforderlich") from error


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
