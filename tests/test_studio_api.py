from pathlib import Path
from io import BytesIO
import asyncio
import tempfile
import unittest
from unittest.mock import Mock

from fastapi import FastAPI
import httpx
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import assets, modules, display
from app.api.deps import get_current_user
from app.database import Base, get_db
from app.services.assets import MAX_ASSET_BYTES, MAX_FRAMES, MAX_UPLOAD, AssetStore
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
        self.app.state.display_service.brightness_lock = asyncio.Lock()
        self.app.state.display_service.led_driver.get_debug_snapshot.return_value = {'brightness':12}
        self.app.include_router(assets.router)
        self.app.include_router(modules.router)
        self.app.include_router(display.router)
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
        first = (await self.client.post('/api/modules', json={"kind": "textbox", "name": "Second text"})).json()
        second = (await self.client.post('/api/modules', json={"kind": "textbox", "name": "Third text"})).json()
        self.assertNotEqual(first['key'], second['key'])
        rows = (await self.client.get('/api/modules')).json()
        ids = [row['id'] for row in reversed(rows)]
        self.assertEqual((await self.client.put('/api/modules/order', json={"ids": ids})).status_code, 200)
        self.assertEqual([r['id'] for r in (await self.client.get('/api/modules')).json()], ids)
        self.assertEqual((await self.client.put('/api/modules/order', json={"ids": ids[:-1]})).status_code, 409)
        self.assertEqual([r['id'] for r in (await self.client.get('/api/modules')).json()], ids)

    async def test_sprite_limit_invalid_import_and_missing_asset(self):
        self.assertEqual((await self.client.post('/api/assets/sprites', content=b'x' * (MAX_ASSET_BYTES + 1))).status_code, 413)
        self.assertEqual((await self.client.post('/api/assets/sprites', json={"name":"bad", "frames":[]})).status_code, 422)
        self.assertEqual((await self.client.post('/api/assets/import', content=b'not an image')).status_code, 422)
        self.assertEqual((await self.client.post('/api/modules', json={"kind":"asset", "name":"Bad", "settings":{"asset_id":"../secret"}})).status_code, 422)

    async def test_long_gif_import_is_listed_and_editable(self):
        buffer = BytesIO()
        frames = [Image.new('RGB', (32, 8), 'red' if i % 2 else 'blue') for i in range(267)]
        frames[0].save(buffer, format='GIF', save_all=True, append_images=frames[1:], duration=100)
        response = await self.client.post('/api/assets/import?name=Long+GIF', content=buffer.getvalue())
        self.assertEqual(response.status_code, 201)
        asset = response.json()
        self.assertEqual(len(asset['frames']), 267)
        self.assertEqual((await self.client.get('/api/assets')).json()[0]['frame_count'], 267)
        loaded = (await self.client.get('/api/assets/' + asset['id'])).json()
        response = await self.client.post('/api/assets/sprites', json={'name': 'Edited copy', 'frames': loaded['frames']})
        self.assertEqual(response.status_code, 201)

    async def test_maximum_sprite_roundtrip_and_upload_size_limit(self):
        response = await self.client.post('/api/assets/sprites', json={'name':'512 bright frames', 'frames':[{'pixels':[0xffffff]*256, 'duration_ms':100}]*MAX_FRAMES})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len((await self.client.get('/api/assets/'+response.json()['id'])).json()['frames']), MAX_FRAMES)
        response = await self.client.post('/api/assets/import', content=b'x' * (MAX_UPLOAD + 1))
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()['detail'], 'Maximal 4 MB')

    async def test_authentication_required_for_library_and_import(self):
        self.app.dependency_overrides.pop(get_current_user)
        self.assertEqual((await self.client.get('/api/assets')).status_code, 401)
        self.assertEqual((await self.client.post('/api/assets/import', content=b'GIF')).status_code, 401)

    async def test_clock_is_separate_and_other_module_rename_still_works(self):
        rows = (await self.client.get('/api/modules')).json()
        self.assertFalse(any(row['key'].split('-')[0] == 'clock' for row in rows))
        self.assertEqual((await self.client.post('/api/modules', json={'kind':'clock','name':'Clock'})).status_code,409)
        row = rows[0]
        response = await self.client.put(f'/api/modules/{row["id"]}', json={**row, "name": "Custom Bitcoin", "settings":{"speed":"nan", "priority_every":99999}})
        self.assertEqual(response.status_code, 200)
        settings = response.json()['settings']
        self.assertEqual(settings['speed'], 1)
        self.assertEqual(settings['priority_every'], 3600)
        self.assertEqual(response.json()['name'], 'Custom Bitcoin')

    async def test_brightness_zero_persists_and_read_is_passive(self):
        self.assertEqual((await self.client.get('/api/display/brightness')).json()['brightness'],12)
        self.assertEqual((await self.client.post('/api/display/brightness',json={'brightness':0})).status_code,200)
        response = (await self.client.get('/api/display/brightness')).json()
        self.assertEqual(response['brightness'],0)
        self.assertTrue(response['persisted'])
        self.app.state.display_service.set_brightness.assert_called_once_with(0)
        self.app.state.display_service.led_driver.get_debug_snapshot.assert_called_with(poll=False)

    async def test_offline_brightness_is_saved_and_invalid_values_rejected(self):
        from app.services.led_driver import SerialException
        self.app.state.display_service.set_brightness.side_effect = SerialException('offline')
        self.app.state.display_service.led_driver.get_debug_snapshot.return_value = {'brightness':3,'serial':{'connected':False}}
        self.assertEqual((await self.client.post('/api/display/brightness',json={'brightness':3})).status_code,503)
        self.assertEqual((await self.client.get('/api/display/brightness')).json()['brightness'],3)
        self.assertFalse((await self.client.get('/api/display/brightness')).json()['connected'])
        for value in (-1,256):
            self.assertEqual((await self.client.post('/api/display/brightness',json={'brightness':value})).status_code,422)
        self.assertEqual((await self.client.get('/api/display/brightness')).json()['brightness'],3)
