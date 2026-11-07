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
        self.assertEqual(VERSION, '0.4.0')
