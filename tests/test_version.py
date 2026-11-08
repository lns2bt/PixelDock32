import unittest

import httpx

from app.main import app
from app.version import VERSION


class VersionTests(unittest.IsolatedAsyncioTestCase):
    async def test_running_version_is_available_without_hardware_or_login(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get('/api/version')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'version': VERSION})
        self.assertEqual(VERSION, '0.5.0')


class CacheBustingTests(unittest.IsolatedAsyncioTestCase):
    async def test_pages_version_assets_and_static_files_revalidate(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            page = await client.get('/login')
            asset = await client.get('/static/retro.css')
        self.assertEqual(page.status_code, 200)
        self.assertIn(f'/static/retro.css?v={VERSION}', page.text)
        self.assertNotIn('retro.css"', page.text)
        self.assertEqual(page.headers['cache-control'], 'no-cache')
        self.assertEqual(asset.status_code, 200)
        self.assertEqual(asset.headers['cache-control'], 'no-cache')
        self.assertIn('etag', asset.headers)
