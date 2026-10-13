import asyncio
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.api import bitcoin, modules
from app.api.deps import get_current_user
from app.database import Base, get_db
from app.models import ModuleConfig
from test_bitcoin_stage import cache


class BitcoinApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine=create_async_engine('sqlite+aiosqlite:///:memory:')
        self.sessions=async_sessionmaker(self.engine,expire_on_commit=False)
        async with self.engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
        async with self.sessions() as db:
            row=ModuleConfig(key='btc',name='Bitcoin',duration_seconds=10,enabled=True,sort_order=0,settings={'private_legacy':'keep'})
            db.add(row);await db.commit();self.id=row.id
        self.app=FastAPI();self.app.include_router(bitcoin.router);self.app.include_router(modules.router)
        self.display=Mock();self.display.cache_provider.return_value=cache();self.display.time_stage=None
        self.display.time_stage_status.return_value={};self.display.brightness_lock=asyncio.Lock()
        self.app.state.display_service=self.display
        async def database():
            async with self.sessions() as db:yield db
        self.app.dependency_overrides[get_db]=database;self.app.dependency_overrides[get_current_user]=lambda:'test'
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://test')

    async def asyncTearDown(self):
        await self.client.aclose();await self.engine.dispose()

    async def settings(self):
        async with self.sessions() as db:return deepcopy((await db.get(ModuleConfig,self.id)).settings)

    async def test_catalog_and_browser_are_passive(self):
        data=(await self.client.get('/api/bitcoin')).json()
        self.assertEqual(len(data['styles']),10);self.assertEqual(len(data['infos']),7)
        before=await self.settings()
        for style in data['styles']:
            response=await self.client.post('/api/bitcoin/preview',json={'module_id':self.id,'style':style['key'],'demo':True,'elapsed':4})
            self.assertEqual(response.status_code,200);self.assertEqual(len(response.json()['pixels']),256)
            self.assertTrue(response.json()['demo'])
        self.assertEqual(await self.settings(),before);self.display.preview_bitcoin.assert_not_called()

    async def test_physical_uses_live_data_and_preserves_persisted_settings(self):
        before=await self.settings()
        response=await self.client.post('/api/bitcoin/preview',json={'module_id':self.id,'physical':True,'info':'sats','style':'orbit'})
        self.assertEqual(response.status_code,200)
        settings=self.display.preview_bitcoin.call_args.args[0]
        self.assertEqual(settings['bitcoin_infos'],['sats'])
        self.assertEqual(await self.settings(),before)

    async def test_sleep_and_simulated_data_cannot_bypass_led_safety(self):
        self.display.time_stage=Mock();self.display.time_stage.sleep_state.return_value={'active':True}
        payload={'module_id':self.id,'physical':True}
        self.assertEqual((await self.client.post('/api/bitcoin/preview',json=payload)).status_code,409)
        for extra in ({'demo':True},{'event':'dock'}):
            self.assertEqual((await self.client.post('/api/bitcoin/preview',json={**payload,**extra})).status_code,422)
        self.display.preview_bitcoin.assert_not_called()

    async def test_unsaved_preview_options_and_timing_are_passive(self):
        before=await self.settings()
        options={'bitcoin_infos':['fees','age','sats'],'bitcoin_max_infos':3,'bitcoin_read_seconds':5,'bitcoin_intensity':'calm'}
        timing=await self.client.post('/api/bitcoin/duration',json={'module_id':self.id,'settings':options})
        self.assertEqual(timing.status_code,200)
        self.assertAlmostEqual(timing.json()['duration'],28.4)
        self.assertEqual(timing.json()['info_count'],3)
        response=await self.client.post('/api/bitcoin/preview',json={'module_id':self.id,'physical':True,'style':'orbit','settings':options})
        self.assertEqual(response.status_code,200)
        snapshot=self.display.preview_bitcoin.call_args.args[0]
        self.assertEqual(snapshot['bitcoin_infos'],options['bitcoin_infos'])
        self.assertEqual(snapshot['bitcoin_read_seconds'],5)
        self.assertEqual(await self.settings(),before)

    async def test_validation_auth_and_settings_roundtrip(self):
        for extra in ({'style':'bad'},{'info':'bad'},{'elapsed':-1},{'event':'bad'},{'module_id':999}):
            self.assertIn((await self.client.post('/api/bitcoin/preview',json={'module_id':self.id,**extra})).status_code,(404,422))
        response=await self.client.put(f'/api/modules/{self.id}',json={'enabled':True,'duration_seconds':10,'sort_order':0,'settings':{'bitcoin_max_infos':2,'bitcoin_infos':['fees','age','sats'],'bitcoin_styles':['train'],'private_legacy':'keep'}})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['settings']['bitcoin_infos'],['fees','age','sats'])
        self.assertEqual(response.json()['settings']['private_legacy'],'keep')
        self.app.dependency_overrides.pop(get_current_user)
        self.assertEqual((await self.client.get('/api/bitcoin')).status_code,401)
