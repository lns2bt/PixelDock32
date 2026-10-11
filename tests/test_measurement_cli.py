from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError


spec = importlib.util.spec_from_file_location("measure_transport", Path("scripts/measure-transport.py"))
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class MeasurementCliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name) / "samples.jsonl"
        self.args = ["measure-transport", "--duration", "0.01", "--output", str(self.output)]

    def test_collects_without_logging_token(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'{"ok":true,"result":{"transport":"serial"}}')
        with patch("sys.argv", self.args), patch.dict("os.environ", {"PIXELDOCK_TOKEN": "test-secret"}), patch.object(cli, "build_opener", return_value=opener), redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(), 0)
        record = json.loads(self.output.read_text().splitlines()[0])
        self.assertTrue(record["metrics"]["ok"])
        self.assertNotIn("test-secret", self.output.read_text())
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
        self.assertTrue(request.full_url.endswith("/api/debug/led/metrics"))

    def test_http_failure_is_retained_and_returns_failure(self):
        opener = Mock()
        opener.open.side_effect = HTTPError("http://localhost", 401, "Unauthorized", {}, None)
        with patch("sys.argv", self.args), patch.dict("os.environ", {"PIXELDOCK_TOKEN": "test-secret"}), patch.object(cli, "build_opener", return_value=opener), redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(), 1)
        self.assertEqual(json.loads(self.output.read_text().splitlines()[0])["error"], "HTTP 401")

    def test_existing_output_is_not_overwritten(self):
        self.output.write_text("keep me")
        with patch("sys.argv", self.args), patch.dict("os.environ", {"PIXELDOCK_TOKEN": "test-secret"}), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                cli.main()
        self.assertEqual(result.exception.code, 1)
        self.assertEqual(self.output.read_text(), "keep me")

    def test_missing_token_is_rejected(self):
        with patch("sys.argv", self.args), patch.dict("os.environ", {"PIXELDOCK_TOKEN": ""}), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                cli.main()
        self.assertEqual(result.exception.code, 2)
        self.assertFalse(self.output.exists())

    def test_invalid_duration_is_rejected(self):
        for value in ("0", "-1", "nan", "inf"):
            with patch("sys.argv", self.args + ["--duration", value]), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    cli.main()

    def test_redirects_are_not_followed(self):
        self.assertIsNone(cli.NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://elsewhere.invalid"))
