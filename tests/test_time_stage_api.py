import asyncio
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from fastapi import FastAPI
import httpx
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import time_stage
from app.api.deps import get_current_user
from app.database import Base, get_db
from app.models import ModuleConfig, TimeStagePreference
from app.services.time_stage import render_scene
from app.services.time_stage.settings import Config, load_or_migrate


class TimeStageApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.app = FastAPI()
        self.display = Mock()
        self.display.brightness_lock = asyncio.Lock()
        self.display.time_stage = None
        self.display.time_stage_config = Config().model_dump(mode="json")
        self.display.astronomy_data = {"sunrise": "2026-10-13T07:00:00+02:00"}
        self.display.time_stage_status.return_value = {"sleep": {"active": False, "mode": "auto"}}
        self.display.configure_time_stage.side_effect = lambda value: setattr(self.display, "time_stage_config", value)
        self.display.render_time_stage_preview.side_effect = render_scene
        self.display.preview_for_browser = self.display.render_time_stage_preview
        self.display.preview_time_stage.return_value = {"ok": True}
        self.app.state.display_service = self.display
        self.app.include_router(time_stage.router)

        async def database():
            async with self.sessions() as db:
                yield db

        self.app.dependency_overrides[get_db] = database
        self.app.dependency_overrides[get_current_user] = lambda: "test"
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.engine.dispose()

    async def persisted(self):
        async with self.sessions() as db:
            preference = await db.get(TimeStagePreference, "config")
            return deepcopy(preference.value) if preference else None

    async def test_named_profiles_roundtrip_and_reject_unsafe_or_wrong_categories(self):
        cfg=Config().model_dump(mode='json')
        cfg['profiles']={'Abend':{'scenes':['retro_cartridge'],'selection':'random'}}
        response=await self.client.put('/api/time-stage',json=cfg)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['config']['profiles']['Abend']['scenes'],['retro_cartridge'])
        cfg['profiles']={'__proto__':{'scenes':['retro_cartridge']}}
        self.assertEqual((await self.client.put('/api/time-stage',json=cfg)).status_code,422)
        cfg=Config().model_dump(mode='json');cfg['events']['hour']['scenes']=['sunrise']
        self.assertEqual((await self.client.put('/api/time-stage',json=cfg)).status_code,422)

    async def test_passive_read_catalog_and_browser_preview(self):
        response = await self.client.get("/api/time-stage")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["config"]["scenes"]), 20)
        self.assertEqual(len(body["catalog"]), 40)
        self.assertEqual(body["astronomy"], self.display.astronomy_data)
        self.assertEqual(body["location"]["source"], "weather")
        self.assertIsNone(await self.persisted())
        response = await self.client.post("/api/time-stage/preview", json={
            "key": "retro_platformer", "at": "2026-10-13T12:34:56", "elapsed": 2,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "12:34")
        self.assertEqual(len(response.json()["frame"]), 8)
        self.assertEqual(len(response.json()["pixels"]), 256)
        now = self.display.render_time_stage_preview.call_args.args[1]
        self.assertEqual(str(now.tzinfo), "Europe/Vienna")
        self.display.preview_time_stage.assert_not_called()
        self.assertEqual(self.display.led_driver.mock_calls, [])
        self.display.configure_time_stage.assert_not_called()

    async def test_put_import_export_and_manual_override_is_not_exported(self):
        config = Config().model_dump(mode="json")
        config["sleep"].update(mode="wake", until="2026-10-13T23:00:00+02:00")
        config["location"] = {"source": "custom", "latitude": 48.2, "longitude": 16.3}
        response = await self.client.put("/api/time-stage", json=config)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(await self.persisted(), config)
        self.display.configure_time_stage.assert_called_once_with(config)
        self.assertEqual(response.json()["location"], config["location"])
        exported = (await self.client.get("/api/time-stage/export")).json()
        self.assertEqual(exported["version"], 1)
        self.assertEqual(exported["config"]["sleep"]["mode"], "auto")
        self.assertIsNone(exported["config"]["sleep"]["until"])
        self.assertEqual((await self.persisted())["sleep"]["mode"], "wake")
        exported["config"]["enabled"] = False
        self.assertEqual((await self.client.post("/api/time-stage/import", json=exported)).status_code, 200)
        self.assertFalse((await self.persisted())["enabled"])

    async def test_invalid_config_import_never_commit(self):
        good = Config().model_dump(mode="json")
        self.assertEqual((await self.client.put("/api/time-stage", json=good)).status_code, 200)
        changes = [
            {"version": 2}, {"timezone": "No/Such_Zone"}, {"unknown": True},
            {"scenes": ["classic"]}, {"weights": {"retro_platformer": 11}},
            {"favorites": ["event_fireworks"]}, {"color": "red"},
            {"location": {"source": "custom", "latitude": 100, "longitude": 0}},
            {"location": {"source": "custom"}},
            {"sleep": {"start": "08:00", "end": "08:00"}},
            {"sleep": {"until": "2026-10-13T12:00:00"}},
            {"events": {"hour": {"scenes": ["retro_platformer"]}}},
            {"events": {"sunrise": {"scenes": ["sunrise"], "panels": ["unknown"]}}},
            {"events": {"unknown": {"scenes": ["event_fireworks"]}}},
        ]
        for change in changes:
            with self.subTest(change=change):
                response = await self.client.post("/api/time-stage/import", json={"version": 1, "config": {**good, **change}})
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(await self.persisted(), good)
        self.assertEqual((await self.client.post("/api/time-stage/import", json={"version": 2, "config": good})).status_code, 422)

    async def test_sleep_override_expiry_validation_and_auto(self):
        for value in (0, -1, 1441):
            self.assertEqual((await self.client.post("/api/time-stage/sleep", json={"mode": "sleep", "minutes": value})).status_code, 422)
        self.assertEqual((await self.client.post("/api/time-stage/sleep", json={"mode": "invalid"})).status_code, 422)
        before = datetime.now().timestamp()
        response = await self.client.post("/api/time-stage/sleep", json={"mode": "wake", "minutes": 10})
        self.assertEqual(response.status_code, 200)
        sleep = (await self.persisted())["sleep"]
        self.assertEqual(sleep["mode"], "wake")
        until = datetime.fromisoformat(sleep["until"])
        self.assertIsNotNone(until.utcoffset())
        self.assertAlmostEqual(until.timestamp() - before, 600, delta=5)
        self.assertEqual((await self.client.post("/api/time-stage/sleep", json={"mode": "sleep"})).status_code, 200)
        self.assertIsNotNone((await self.persisted())["sleep"]["until"])
        self.assertEqual((await self.client.post("/api/time-stage/sleep", json={"mode": "auto"})).status_code, 200)
        self.assertIsNone((await self.persisted())["sleep"]["until"])

    async def test_physical_preview_requires_wake_confirmation_and_ignores_at(self):
        self.display.time_stage_status.return_value = {"sleep": {"active": True}}
        payload = {"key": "sunrise", "physical": True, "at": "2000-01-01T12:00:00"}
        self.assertEqual((await self.client.post("/api/time-stage/preview", json=payload)).status_code, 409)
        self.display.preview_time_stage.assert_not_called()
        self.assertEqual((await self.client.post("/api/time-stage/preview", json={**payload, "confirm_wake": True})).status_code, 200)
        self.display.preview_time_stage.assert_called_once_with("sunrise", confirm_wake=True)
        self.display.render_time_stage_preview.assert_not_called()
        for change in ({"key": "unknown"}, {"elapsed": -1}, {"elapsed": 121}):
            self.assertEqual((await self.client.post("/api/time-stage/preview", json={**payload, **change})).status_code, 422)

    async def test_all_routes_require_authentication(self):
        self.app.dependency_overrides.pop(get_current_user)
        for method, path, payload in (
            ("GET", "", None), ("GET", "/export", None),
            ("PUT", "", {}), ("POST", "/import", {"version": 1, "config": {}}),
            ("POST", "/sleep", {"mode": "auto"}),
            ("POST", "/preview", {"key": "retro_platformer"}),
        ):
            response = await self.client.request(method, "/api/time-stage" + path, json=payload)
            self.assertEqual(response.status_code, 401)

    async def test_migration_archives_full_rows_disables_only_clocks_and_is_idempotent(self):
        rows = [
            ModuleConfig(key="clock", name="Disabled", enabled=False, duration_seconds=8, sort_order=0, settings={"color": "#123456"}),
            ModuleConfig(key="clock-second", name="Selected", enabled=True, duration_seconds=12, sort_order=1,
                         settings={"timezone": "UTC", "priority_every": 35, "color": "#abcdef", "variants": ["classic", "binary", "flip"]}),
            ModuleConfig(key="clock-third", name="Other", enabled=True, duration_seconds=9, sort_order=2, settings={"untouched": [1, 2]}),
            ModuleConfig(key="weather", name="Weather", enabled=True, duration_seconds=10, sort_order=3, settings={"color": "#010203"}),
        ]
        async with self.sessions() as db:
            db.add_all(rows)
            await db.commit()
            original = [{column.name: deepcopy(getattr(row, column.name)) for column in ModuleConfig.__table__.columns} for row in rows]
            config = await load_or_migrate(db, SimpleNamespace(tz="Europe/Vienna"))
            self.assertEqual(config["timezone"], "UTC")
            self.assertEqual(config["duration_seconds"], 12)
            self.assertEqual(config["interval_seconds"], 35)
            self.assertIsNone(config["color"])
            self.assertEqual(config["scenes"][:3], ["retro_cartridge", "craft_binary_precision", "craft_mechanical_flip"])
            self.assertEqual(len(config["scenes"]), 20)
            archive = await db.get(TimeStagePreference, "legacy_clocks")
            self.assertEqual(archive.value, original[:3])
            migrated = list((await db.scalars(select(ModuleConfig).order_by(ModuleConfig.sort_order))).all())
            for row, expected in zip(migrated, original):
                actual = {column.name: getattr(row, column.name) for column in ModuleConfig.__table__.columns}
                self.assertEqual(actual, {**expected, "enabled": False} if row.key.startswith("clock") else expected)
            self.assertEqual(await load_or_migrate(db, SimpleNamespace(tz="UTC")), config)
            self.assertEqual(archive.value, original[:3])

    async def test_all_disabled_clocks_and_unsupported_persisted_version(self):
        async with self.sessions() as db:
            db.add(ModuleConfig(key="clock", name="Clock", enabled=False, duration_seconds=8, sort_order=0, settings={}))
            await db.commit()
            config = await load_or_migrate(db, SimpleNamespace(tz="UTC"))
            self.assertFalse(config["enabled"])
            preference = await db.get(TimeStagePreference, "config")
            preference.value = {**config, "version": 99}
            await db.commit()
            with self.assertRaises(ValidationError):
                await load_or_migrate(db, SimpleNamespace(tz="UTC"))
            self.assertEqual(preference.value["version"], 99)
