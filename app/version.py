"""Read the deployed version once, so it describes the running process."""

from pathlib import Path

VERSION = (Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()
