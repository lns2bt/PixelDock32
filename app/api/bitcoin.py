"""Passive Bitcoin catalog/data/browser previews and explicit module LED playback."""
import asyncio
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from app.api.deps import get_current_user
from app.database import get_db
from app.models import ModuleConfig
from app.services.bitcoin_stage import catalog, normalize, Director, render, info_value, STYLES, INFOS, EVENTS

router = APIRouter(prefix='/api/bitcoin', tags=['bitcoin'], dependencies=[Depends(get_current_user)])


class Preview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    module_id: int
    style: str = 'forge'
    info: str | None = None
    elapsed: float = Field(default=0,ge=0,le=300,allow_inf_nan=False)
    event: str | None = None
    physical: bool = False
    demo: bool = False
    settings: dict | None = Field(default=None, max_length=128)


class TimingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    module_id: int | None = None
    settings: dict = Field(default_factory=dict, max_length=128)


def _preview_options(settings):
    if 'bitcoin_infos' in settings and (not isinstance(settings['bitcoin_infos'],list) or not settings['bitcoin_infos']):
        raise HTTPException(422, 'Bitte mindestens eine Bitcoin-Info auswählen.')
    return settings


@router.post('/duration')
async def duration(payload: TimingRequest, request: Request, db=Depends(get_db)):
    from app.services.bitcoin_stage import presentation_timing
    settings = {}
    if payload.module_id is not None:
        row = await db.get(ModuleConfig, payload.module_id)
        if row is None or row.key.split('-')[0] != 'btc':
            raise HTTPException(404, 'Bitcoin-Modul nicht gefunden')
        settings = row.settings or {}
    return presentation_timing(_preview_options({**settings, **payload.settings}))


@router.get('')
async def get_bitcoin(request: Request):
    service=request.app.state.display_service
    cache=dict(service.cache_provider() or {})
    settings=normalize({})
    return {**catalog(), 'data':[info_value(key,cache,settings) for key in INFOS],
            'fee_source':'mempool.space (oder BTC_NETWORK_API_URL)',
            'price_source':'Konfigurierte BTC_API_URL',
            'sleep':service.time_stage_status().get('sleep',{})}


@router.post('/preview')
async def preview(payload: Preview, request: Request, db=Depends(get_db)):
    if payload.style not in STYLES or payload.info is not None and payload.info not in INFOS or payload.event is not None and payload.event not in EVENTS:
        raise HTTPException(422,'Unbekannte Bitcoin-Szene oder Information')
    row=await db.get(ModuleConfig,payload.module_id)
    if row is None or row.key.split('-')[0]!='btc': raise HTTPException(404,'Bitcoin-Modul nicht gefunden')
    service=request.app.state.display_service
    settings=normalize(_preview_options({**(row.settings or {}), **(payload.settings or {})}))
    settings.update(bitcoin_stage=True,visual_style='retro',bitcoin_styles=[payload.style])
    if payload.info: settings.update(bitcoin_infos=[payload.info],bitcoin_max_infos=1)
    if payload.physical:
        if payload.demo or payload.event: raise HTTPException(422,'Beispieldaten und simulierte Blockereignisse sind nur im Browser erlaubt')
        if service.time_stage and service.time_stage.sleep_state(service._stage_now())['active']:
            raise HTTPException(409,'Schlafmodus aktiv. Bitte zuerst ausdrücklich auf Wach umschalten.')
        try:
            service.preview_bitcoin(settings)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {'ok':True,'physical':True}
    cache=dict(service.cache_provider() or {})
    if payload.demo:
        now=time.time()
        cache.update(btc_eur=65432,btc_block_height=960123,btc_change_24h=2.7,
                     btc_updated_at=now,btc_error=None,btc_block_height_updated_at=now,btc_block_height_error=None,
                     btc_block_time=now-420,btc_block_details_updated_at=now,btc_block_details_error=None,
                     btc_fees={'halfHourFee':3},btc_fees_updated_at=now,btc_fees_error=None)
    visit=Director().begin(settings,cache,preview=True)
    if payload.event:
        visit.event=payload.event;visit.old_height=960122;visit.new_height=960123
    result=await asyncio.to_thread(render,visit,payload.elapsed)
    return {'pixels':[(rgb[0]<<16)|(rgb[1]<<8)|rgb[2] if rgb else 0 for line in result.color_frame for rgb in line],
            'text':result.text,'scene_key':result.scene_key,'duration':visit.duration,
            'demo':payload.demo or bool(payload.event), 'info':visit.infos}
