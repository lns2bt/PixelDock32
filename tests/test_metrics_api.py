from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.debug import router
from app.api.deps import get_current_user


class MetricsApiTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.driver = Mock()
        self.driver.get_transport_metrics.return_value = {"transport": "serial"}
        self.app.state.display_service = SimpleNamespace(led_driver=self.driver)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def test_authentication_required(self):
        self.assertEqual(self.client.get("/api/debug/led/metrics").status_code, 401)
        self.driver.get_transport_metrics.assert_not_called()

    def test_passive_route_does_not_poll_hardware(self):
        self.app.dependency_overrides[get_current_user] = lambda: "test-user"
        response = self.client.get("/api/debug/led/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "result": {"transport": "serial"}})
        self.driver.get_transport_metrics.assert_called_once()
        self.driver.get_debug_snapshot.assert_not_called()

    def test_unavailable_service(self):
        self.app.dependency_overrides[get_current_user] = lambda: "test-user"
        del self.app.state.display_service
        self.assertEqual(self.client.get("/api/debug/led/metrics").status_code, 503)
