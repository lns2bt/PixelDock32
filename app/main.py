import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import re

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, debug, display, modules, assets, time_stage, bitcoin, weather
from app.config import get_settings
from app.database import SessionLocal, Base, engine
from app.services.display import DisplayService
from app.services.external_data import ExternalDataService
from app.services.led_driver import LEDDriver
from app.services.led_mapper import LEDMapper
from app.services.module_manager import ensure_default_modules
from app.services.bitmap_loader import BitmapLoader
from app.services.assets import AssetStore
from app.services.retro_scenes import seed_retro_assets
from app.models import DisplayPreference
from app.services.time_stage.settings import load_or_migrate
from app.version import VERSION

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    led_driver = None
    ext_service = None
    display_service = None
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with SessionLocal() as db:
            await ensure_default_modules(db)
            brightness = await db.get(DisplayPreference, "brightness")
            runtime_settings = settings
            if brightness is not None and 0 <= brightness.value <= 255:
                runtime_settings = settings.model_copy(update={"led_brightness": brightness.value})
            stage_config = await load_or_migrate(db, settings)

        ext_service = ExternalDataService(settings)
        led_driver = await asyncio.to_thread(LEDDriver, runtime_settings)
        mapper = LEDMapper(settings)
        asset_store = await asyncio.to_thread(AssetStore, settings.asset_directory)
        await asyncio.to_thread(seed_retro_assets, asset_store)
        app.state.asset_store = asset_store
        bitmap_dir = Path(__file__).parent / "bitmaps"
        bitmap_dir.mkdir(parents=True, exist_ok=True)
        display_service = DisplayService(
            session_factory=SessionLocal,
            led_driver=led_driver,
            mapper=mapper,
            cache_provider=lambda: ext_service.cache,
            fps=settings.render_fps,
            bitmap_loader=BitmapLoader(bitmap_dir),
            asset_store=asset_store,
        )
        app.state.external_data_service = ext_service
        app.state.display_service = display_service
        display_service.configure_time_stage(stage_config)
        await ext_service.start()
        await display_service.start()
        yield
    finally:
        try:
            if display_service is not None:
                await display_service.stop()
        finally:
            try:
                if ext_service is not None:
                    await ext_service.stop()
            finally:
                try:
                    if led_driver is not None:
                        await asyncio.to_thread(led_driver.close)
                finally:
                    await engine.dispose()


app = FastAPI(title=settings.app_name, version=VERSION, lifespan=lifespan)


@app.get("/api/version")
async def version():
    return {"version": VERSION}
app.include_router(auth.router)
app.include_router(modules.router)
app.include_router(display.router)
app.include_router(debug.router)
app.include_router(assets.router)
app.include_router(time_stage.router)
app.include_router(bitcoin.router)
app.include_router(weather.router)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

_ASSET_URL = re.compile(r'(/static/[\w./-]+\.(?:css|js))(?:\?v=[^"\']*)?')
NO_CACHE = {"Cache-Control": "no-cache"}


@app.middleware("http")
async def revalidate_static(request: Request, call_next):
    """Static files are revalidated (ETag → 304) so updates show up at once."""
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def _page(name: str) -> HTMLResponse:
    """Serve a page with versioned asset URLs: a release never mixes old CSS with new JS."""
    html = (static_dir / name).read_text(encoding="utf-8")
    return HTMLResponse(_ASSET_URL.sub(lambda m: f"{m.group(1)}?v={VERSION}", html), headers=NO_CACHE)


@app.get("/")
async def root():
    return _page("dashboard.html")


@app.get("/modules")
async def modules_page():
    return _page("playlist.html")


@app.get("/debug")
async def debug_page():
    return _page("debug.html")


@app.get("/tools")
async def tools_page():
    return _page("tools.html")


@app.get("/mapping")
async def mapping_page():
    return _page("mapping.html")


@app.get("/login")
async def login_page():
    return _page("login.html")


@app.get("/studio")
async def studio_page():
    return _page("studio.html")


@app.get("/advanced")
async def advanced_page():
    return _page("advanced.html")


@app.get("/time-stage")
async def time_stage_page():
    return _page("time-stage.html")


@app.get("/bitcoin")
async def bitcoin_page():
    return _page("bitcoin.html")


@app.get('/weather')
async def weather_page():
    return _page('weather.html')
