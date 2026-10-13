import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, debug, display, modules, assets, time_stage
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


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(auth.router)
app.include_router(modules.router)
app.include_router(display.router)
app.include_router(debug.router)
app.include_router(assets.router)
app.include_router(time_stage.router)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    return FileResponse(static_dir / "dashboard.html")


@app.get("/modules")
async def modules_page():
    return FileResponse(static_dir / "playlist.html")


@app.get("/debug")
async def debug_page():
    return FileResponse(static_dir / "debug.html")


@app.get("/tools")
async def tools_page():
    return FileResponse(static_dir / "tools.html")


@app.get("/mapping")
async def mapping_page():
    return FileResponse(static_dir / "mapping.html")


@app.get("/login")
async def login_page():
    return FileResponse(static_dir / "login.html")


@app.get("/studio")
async def studio_page():
    return FileResponse(static_dir / "studio.html")


@app.get("/advanced")
async def advanced_page():
    return FileResponse(static_dir / "advanced.html")


@app.get("/time-stage")
async def time_stage_page():
    return FileResponse(static_dir / "time-stage.html")
