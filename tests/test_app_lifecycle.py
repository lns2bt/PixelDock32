from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_user
from app.config import Settings
import app.main as main


class AppLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.settings = Settings(_env_file=None, led_transport="mock", dht_enabled=False, mapping_state_file=str(Path(directory.name) / "mapping.json"))
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.external = Mock(cache={}, start=AsyncMock(), stop=AsyncMock(), _tasks=[], _running=False, settings=self.settings)
        for name, replacement in (("settings", self.settings), ("engine", self.engine), ("SessionLocal", self.sessions)):
            patcher = patch.object(main, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(main, "ExternalDataService", return_value=self.external)
        patcher.start()
        self.addCleanup(patcher.stop)
        main.app.dependency_overrides[get_current_user] = lambda: "test-user"
        self.addCleanup(main.app.dependency_overrides.pop, get_current_user)

    async def test_full_lifespan_with_database_and_mock_display(self):
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
                result = await client.get("/api/debug/led/metrics")
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()["result"]["transport"], "mock")
                self.assertEqual((await client.post("/api/display/text", json={"text": "PIXEL", "seconds": 2})).status_code, 200)
                self.assertEqual((await client.get("/api/debug/status")).status_code, 200)
                display = main.app.state.display_service
                self.assertEqual(display.target_fps, 30)
        self.assertFalse(display._running)
        self.assertTrue(display._task.done())
        self.external.stop.assert_awaited_once()

    async def test_initialization_failure_closes_initialized_driver(self):
        driver = Mock()
        with patch.object(main, "LEDDriver", return_value=driver), patch.object(main, "LEDMapper", side_effect=RuntimeError("mapping failure")):
            with self.assertRaisesRegex(RuntimeError, "mapping failure"):
                async with main.lifespan(main.app):
                    pass
        driver.close.assert_called_once()
        self.external.stop.assert_awaited_once()
