import asyncio
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from fastapi import FastAPI
import httpx

from app.api.debug import router as debug_router
from app.api.display import router as display_router
from app.api.deps import get_current_user


class NonblockingApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_hardware_calls_leave_event_loop_available(self):
        cases = (
            ("POST", "/api/debug/dht/read-once", {}, "external", "read_dht_debug_snapshot"),
            ("GET", "/api/debug/gpio/environment", None, "external", "get_gpio_environment_report"),
            ("POST", "/api/debug/gpio/output-test", {"gpio_pin": 4}, "external", "run_gpio_output_test"),
            ("POST", "/api/debug/gpio/input-probe", {"gpio_pin": 4}, "external", "run_gpio_input_probe"),
            ("GET", "/api/debug/led", None, "driver", "get_debug_snapshot"),
            ("POST", "/api/debug/led/serial-ping", {}, "driver", "serial_ping"),
            ("POST", "/api/display/brightness", {"brightness": 100}, "display", "set_brightness"),
        )
        for method, path, body, owner, function in cases:
            with self.subTest(path=path):
                app = FastAPI()
                app.include_router(debug_router)
                app.include_router(display_router)
                app.dependency_overrides[get_current_user] = lambda: "test-user"
                driver, display, external = Mock(), Mock(), Mock()
                display.led_driver = driver
                driver.get_transport_metrics.return_value = {"transport": "serial"}
                app.state.display_service = display
                app.state.external_data_service = external
                started, release = threading.Event(), threading.Event()

                def hardware_call(*args, **kwargs):
                    started.set()
                    if not release.wait(3):
                        raise RuntimeError("test release timeout: event loop blocked")
                    return {"ok": True}

                getattr({"external": external, "driver": driver, "display": display}[owner], function).side_effect = hardware_call
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    operation = asyncio.create_task(client.request(method, path, json=body))
                    try:
                        self.assertTrue(await asyncio.to_thread(started.wait, 1))
                        self.assertFalse(operation.done())
                        response = await asyncio.wait_for(client.get("/api/debug/led/metrics"), timeout=0.5)
                        self.assertEqual(response.status_code, 200)
                    finally:
                        release.set()
                        response = await operation
                    self.assertEqual(response.status_code, 200)
