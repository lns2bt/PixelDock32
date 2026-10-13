from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from fastapi import FastAPI
import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import assets, modules
from app.api.deps import get_current_user
from app.database import Base, get_db
from app.services.assets import AssetStore
from app.services.module_manager import ensure_default_modules


class StudioApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with self.sessions() as db:
            await ensure_default_modules(db)
        self.app = FastAPI()
        self.app.state.asset_store = AssetStore(directory.name)
        self.app.state.display_service = Mock()
        self.app.include_router(assets.router)
        self.app.include_router(modules.router)
        async def database():
            async with self.sessions() as db:
                yield db
        self.app.dependency_overrides[get_db] = database
        self.app.dependency_overrides[get_current_user] = lambda: "test"
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.engine.dispose()

    async def sprite(self):
        response = await self.client.post('/api/assets/sprites', json={"name": "Sprite", "frames": [{"pixels": [0x123456] * 256, "duration_ms": 100}]})
        self.assertEqual(response.status_code, 201)
        return response.json()

    async def test_asset_to_module_play_and_delete_guards(self):
        asset = await self.sprite()
        response = await self.client.post('/api/modules', json={"kind": "asset", "name": "Test", "enabled": False, "settings": {"asset_id": asset["id"]}})
        self.assertEqual(response.status_code, 201)
        module = response.json()
        self.assertFalse(module['enabled'])
        self.assertEqual((await self.client.post(f'/api/modules/{module["id"]}/play')).status_code, 200)
        self.app.state.display_service.play_once.assert_called_once()
        self.assertEqual((await self.client.delete('/api/assets/' + asset['id'])).status_code, 409)
        self.assertEqual((await self.client.delete(f'/api/modules/{module["id"]}')).status_code, 200)
        self.assertEqual((await self.client.delete('/api/assets/' + asset['id'])).status_code, 200)

    async def test_multiple_same_kind_and_atomic_order(self):
        first = (await self.client.post('/api/modules', json={"kind": "clock", "name": "Second clock"})).json()
        second = (await self.client.post('/api/modules', json={"kind": "clock", "name": "Third clock"})).json()
        self.assertNotEqual(first['key'], second['key'])
        rows = (await self.client.get('/api/modules')).json()
        ids = [row['id'] for row in reversed(rows)]
        self.assertEqual((await self.client.put('/api/modules/order', json={"ids": ids})).status_code, 200)
        self.assertEqual([r['id'] for r in (await self.client.get('/api/modules')).json()], ids)
        self.assertEqual((await self.client.put('/api/modules/order', json={"ids": ids[:-1]})).status_code, 409)
        self.assertEqual([r['id'] for r in (await self.client.get('/api/modules')).json()], ids)

    async def test_sprite_limit_invalid_import_and_missing_asset(self):
        self.assertEqual((await self.client.post('/api/assets/sprites', content=b'x' * 512001)).status_code, 413)
        self.assertEqual((await self.client.post('/api/assets/sprites', json={"name":"bad", "frames":[]})).status_code, 422)
        self.assertEqual((await self.client.post('/api/assets/import', content=b'not an image')).status_code, 422)
        self.assertEqual((await self.client.post('/api/modules', json={"kind":"asset", "name":"Bad", "settings":{"asset_id":"../secret"}})).status_code, 422)

    async def test_authentication_required_for_library_and_import(self):
        self.app.dependency_overrides.pop(get_current_user)
        self.assertEqual((await self.client.get('/api/assets')).status_code, 401)
        self.assertEqual((await self.client.post('/api/assets/import', content=b'GIF')).status_code, 401)

    async def test_clock_settings_validation_and_rename(self):
        row = (await self.client.get('/api/modules')).json()[0]
        response = await self.client.put(f'/api/modules/{row["id"]}', json={**row, "name": "Arcade Clock", "settings":{"variants":[], "speed":"nan", "priority_every":99999}})
        self.assertEqual(response.status_code, 200)
        settings = response.json()['settings']
        self.assertEqual(settings['variants'], ['classic'])
        self.assertEqual(settings['speed'], 1)
        self.assertEqual(settings['priority_every'], 3600)
        self.assertEqual(response.json()['name'], 'Arcade Clock')
