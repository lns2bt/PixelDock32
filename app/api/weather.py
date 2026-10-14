"""Passive weather catalog/timing/browser previews and explicit live LED previews."""
import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_current_user
from app.database import get_db
from app.models import ModuleConfig
from app.services.weather_stage import (
    Director, INFOS, STYLES, catalog, info_value, normalize, presentation_timing, render,
)

router = APIRouter(prefix='/api/weather', tags=['weather'], dependencies=[Depends(get_current_user)])
WMO_CODES = frozenset((0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65,
                       66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99))


class Preview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    module_id: int
    style: str = 'home'
    info: str | None = None
    elapsed: float = Field(default=0, ge=0, le=300, allow_inf_nan=False)
    physical: bool = False
    demo: bool = False
    condition: int | None = Field(default=None, strict=True)
    is_day: bool | None = None
    settings: dict | None = Field(default=None, max_length=128)


class TimingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    module_id: int | None = None
    settings: dict = Field(default_factory=dict, max_length=128)


def _preview_options(settings):
    # normalize() is forgiving for old stored settings; explicit API selections
    # must not silently turn an empty/invalid selection into the defaults.
    for key, allowed in (('weather_infos', INFOS), ('weather_styles', STYLES)):
        if key in settings:
            values = settings[key]
            if not isinstance(values, list) or not values or any(
                not isinstance(value, str) or value not in allowed for value in values
            ):
                raise HTTPException(422, 'Bitte gültige Wetter-Infos und Szenen auswählen.')
    return settings


async def _weather_row(db, module_id):
    row = await db.get(ModuleConfig, module_id)
    if row is None or row.key.split('-')[0] != 'weather':
        raise HTTPException(404, 'Wetter-Modul nicht gefunden')
    return row


@router.get('')
async def get_weather(request: Request):
    service = request.app.state.display_service
    cache = dict(service.cache_provider() or {})
    settings = normalize({})
    source_settings = getattr(getattr(request.app.state, 'external_data_service', None), 'settings', None)
    location = None if source_settings is None else {
        'latitude': source_settings.weather_lat, 'longitude': source_settings.weather_lon,
        'postcode': source_settings.weather_postcode, 'country': source_settings.weather_country,
        'poll_seconds': source_settings.poll_weather_seconds,
    }
    return {**catalog(), 'data': [info_value(key, cache, settings) for key in INFOS],
            'location': location,
            'source': 'Modellbasierte Open-Meteo Current Conditions für den konfigurierten Standort; keine lokale Wetterbeobachtung.',
            'sleep': service.time_stage_status().get('sleep', {})}


@router.post('/duration')
async def duration(payload: TimingRequest, db=Depends(get_db)):
    settings = {}
    if payload.module_id is not None:
        row = await _weather_row(db, payload.module_id)
        settings = row.settings or {}
    return presentation_timing(_preview_options({**settings, **payload.settings}))


@router.post('/preview')
async def preview(payload: Preview, request: Request, db=Depends(get_db)):
    if (payload.style not in STYLES or
            payload.info is not None and payload.info not in INFOS or
            payload.condition is not None and payload.condition not in WMO_CODES):
        raise HTTPException(422, 'Unbekannte Wetter-Szene, Information oder WMO-Bedingung')
    simulated = payload.condition is not None or payload.is_day is not None
    if simulated and not payload.demo or payload.physical and (payload.demo or simulated):
        raise HTTPException(422, 'Beispieldaten und simulierte Wetterbedingungen sind nur in Browser-Demos erlaubt')
    row = await _weather_row(db, payload.module_id)
    settings = normalize(_preview_options({**(row.settings or {}), **(payload.settings or {})}))
    settings.update(weather_stage=True, weather_styles=[payload.style])
    if payload.info is not None:
        settings.update(weather_infos=[payload.info], weather_max_infos=1)
    service = request.app.state.display_service
    if payload.physical:
        sleep = service.time_stage_status().get('sleep', {})
        if sleep.get('active') or (service.time_stage is not None and
                service.time_stage.sleep_state(service._stage_now())['active']):
            raise HTTPException(409, 'Schlafmodus aktiv. Bitte zuerst ausdrücklich auf Wach umschalten.')
        try:
            service.preview_weather(settings)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {'ok': True, 'physical': True}
    cache = dict(service.cache_provider() or {})
    if payload.demo:
        now = time.time()
        cache.update(weather_temp=12, weather_outdoor_temp=12, weather_indoor_temp=22,
                     weather_indoor_humidity=48, weather_updated_at=now,
                     weather_outdoor_updated_at=now, dht_updated_at=now,
                     weather_error=None, weather_outdoor_error=None, dht_error=None,
                      weather_code=payload.condition if payload.condition is not None else 0,
                      weather_is_day=payload.is_day if payload.is_day is not None else True,
                      weather_precipitation=1.2 if payload.condition in (61,63,65,80,81,82,95) else 0,
                      weather_wind_speed=8, weather_outdoor_trend=None,
                      weather_indoor_trend=None, weather_humidity_trend=None)
    visit = Director().begin(settings, cache, preview=True)
    result = await asyncio.to_thread(render, visit, payload.elapsed)
    return {'pixels': [(rgb[0] << 16) | (rgb[1] << 8) | rgb[2] if rgb else 0
                       for line in result.color_frame for rgb in line],
            'text': result.text, 'scene_key': result.scene_key, 'duration': visit.duration,
            'demo': payload.demo, 'info': visit.infos}
