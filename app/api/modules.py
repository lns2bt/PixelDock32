from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models import ModuleConfig
from app.schemas import ModuleConfigResponse, ModuleConfigUpdate
from app.services.module_manager import list_modules

router = APIRouter(prefix="/api/modules", tags=["modules"])


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
    module.settings = payload.settings
    await db.commit()
    await db.refresh(module)
    return module
