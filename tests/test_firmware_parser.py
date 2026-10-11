from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class FirmwareParserTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("g++"), "g++ required for native firmware parser test")
    def test_actual_sketch_parser_with_host_stubs(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "parser-test"
            subprocess.run([
                "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                "-Itests/firmware", "tests/firmware/parser_harness.cpp", "-o", str(binary),
            ], check=True, capture_output=True, text=True, timeout=30)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.stdout.strip(), "firmware-parser-ok")
