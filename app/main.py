from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, debug, display, modules
from app.config import get_settings
from app.database import SessionLocal, Base, engine
from app.services.display import DisplayService
from app.services.external_data import ExternalDataService
from app.services.led_driver import LEDDriver
from app.services.led_mapper import LEDMapper
from app.services.module_manager import ensure_default_modules
from app.services.bitmap_loader import BitmapLoader

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        await ensure_default_modules(db)

    ext_service = ExternalDataService(settings)
    led_driver = LEDDriver(settings)
    mapper = LEDMapper(settings)
    bitmap_dir = Path(__file__).parent / "bitmaps"
    bitmap_dir.mkdir(parents=True, exist_ok=True)
    display_service = DisplayService(
        session_factory=SessionLocal,
        led_driver=led_driver,
        mapper=mapper,
        cache_provider=lambda: ext_service.cache,
        fps=settings.render_fps,
        bitmap_loader=BitmapLoader(bitmap_dir),
    )

    app.state.external_data_service = ext_service
    app.state.display_service = display_service

    await ext_service.start()
    await display_service.start()

    yield

    await display_service.stop()
    await ext_service.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(auth.router)
app.include_router(modules.router)
app.include_router(display.router)
app.include_router(debug.router)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    return FileResponse(static_dir / "index.html")


@app.get("/modules")
async def modules_page():
    return FileResponse(static_dir / "modules.html")


@app.get("/debug")
async def debug_page():
    return FileResponse(static_dir / "debug.html")


@app.get("/tools")
async def tools_page():
    return FileResponse(static_dir / "tools.html")


@app.get("/login")
async def login_page():
    return FileResponse(static_dir / "login.html")
