#!/usr/bin/env python3
"""Local UI fixture: isolated temporary data, mock LEDs, no network/sensor polls."""

import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    with tempfile.TemporaryDirectory(prefix="pixeldock-ui-") as directory:
        os.environ.update(
            LED_TRANSPORT="mock", DHT_ENABLED="false",
            DATABASE_URL="sqlite+aiosqlite:///" + directory + "/test.db",
            ASSET_DIRECTORY=directory + "/assets", MAPPING_STATE_FILE=directory + "/mapping.json",
            SECRET_KEY="local-ui-test-only", ADMIN_USERNAME="admin", ADMIN_PASSWORD="local-ui-test-only",
        )
        import app.main as app_main
        import uvicorn

        class ExternalFixture:
            def __init__(self, settings):
                self.cache = {}
                self.settings = settings
                self._tasks = []
                self._running = False

            async def start(self):
                self._running = True

            async def stop(self):
                self._running = False

        app_main.ExternalDataService = ExternalFixture
        uvicorn.run(app_main.app, host="127.0.0.1", port=8765, log_level="warning")


if __name__ == "__main__":
    main()
