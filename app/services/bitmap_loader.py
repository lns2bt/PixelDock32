from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from app.services.rendering import blank_color_frame, blank_frame

Color = tuple[int, int, int]


@dataclass
class BitmapFile:
    width: int
    height: int
    pixels: list[list[Color | None]]
    is_monochrome: bool


class BitmapLoader:
    """Loads bitmap files (mono + RGB) and caches parsed output by mtime."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir.resolve()
        self._cache: dict[Path, tuple[float, BitmapFile]] = {}

    def load(self, relative_path: str) -> BitmapFile:
        source_path = self._resolve(relative_path)
        stat = source_path.stat()
        cached = self._cache.get(source_path)
        if cached and cached[0] == stat.st_mtime:
            return cached[1]

        content = source_path.read_text(encoding="utf-8")
        parsed = self._parse(content)
        self._cache[source_path] = (stat.st_mtime, parsed)
        return parsed

    def render_window(
        self,
        bitmap: BitmapFile,
        scroll_direction: str,
        scroll_speed: float,
        now: float | None = None,
    ) -> tuple[list[list[int]], list[list[Color | None]]]:
        frame = blank_frame(32, 8)
        colors = blank_color_frame(32, 8)
        if bitmap.width != 32:
            return frame, colors

        height = bitmap.height
        if height <= 0:
            return frame, colors

        window_start = 0
        if height > 8:
            max_start = height - 8
            speed = max(scroll_speed, 0.25)
            tick = int((now or time.time()) * speed)
            cycle = max_start + 1
            if scroll_direction == "bottom_to_top":
                window_start = max_start - (tick % cycle)
            else:
                window_start = tick % cycle

        for y in range(8):
            src_y = y + window_start
            if src_y >= height:
                break
            for x in range(32):
                color = bitmap.pixels[src_y][x]
                if color is None:
                    continue
                frame[y][x] = 1
                colors[y][x] = color

        return frame, colors

    def _resolve(self, relative_path: str) -> Path:
        requested = (self.base_dir / relative_path).resolve()
        if self.base_dir not in requested.parents and requested != self.base_dir:
            raise ValueError("bitmap path must stay inside bitmap directory")
        if not requested.exists() or not requested.is_file():
            raise ValueError(f"bitmap file not found: {relative_path}")
        return requested

    @staticmethod
    def _parse(content: str) -> BitmapFile:
        stripped = content.lstrip()
        if stripped.startswith("P1"):
            return BitmapLoader._parse_p1(content)
        if stripped.startswith("P3"):
            return BitmapLoader._parse_p3(content)
        return BitmapLoader._parse_plain_grid(content)

    @staticmethod
    def _strip_comments_and_tokens(content: str) -> list[str]:
        tokens: list[str] = []
        for line in content.splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                tokens.extend(line.split())
        return tokens

    @staticmethod
    def _parse_p1(content: str) -> BitmapFile:
        tokens = BitmapLoader._strip_comments_and_tokens(content)
        if len(tokens) < 3 or tokens[0] != "P1":
            raise ValueError("invalid PBM header (expected P1)")

        width = int(tokens[1])
        height = int(tokens[2])
        expected = width * height
        values = tokens[3:]
        if len(values) < expected:
            raise ValueError("not enough bitmap pixels in file")

        pixels: list[list[Color | None]] = [[None for _ in range(width)] for _ in range(height)]
        idx = 0
        for y in range(height):
            for x in range(width):
                pixels[y][x] = (255, 255, 255) if values[idx] == "1" else None
                idx += 1

        return BitmapFile(width=width, height=height, pixels=pixels, is_monochrome=True)

    @staticmethod
    def _parse_p3(content: str) -> BitmapFile:
        tokens = BitmapLoader._strip_comments_and_tokens(content)
        if len(tokens) < 4 or tokens[0] != "P3":
            raise ValueError("invalid PPM header (expected P3)")

        width = int(tokens[1])
        height = int(tokens[2])
        max_value = int(tokens[3])
        if max_value <= 0:
            raise ValueError("invalid PPM max value")

        expected = width * height * 3
        values = tokens[4:]
        if len(values) < expected:
            raise ValueError("not enough color values in PPM file")

        pixels: list[list[Color | None]] = [[None for _ in range(width)] for _ in range(height)]
        idx = 0
        for y in range(height):
            for x in range(width):
                r = int(values[idx])
                g = int(values[idx + 1])
                b = int(values[idx + 2])
                idx += 3
                rr = max(0, min(255, int(round((r / max_value) * 255))))
                gg = max(0, min(255, int(round((g / max_value) * 255))))
                bb = max(0, min(255, int(round((b / max_value) * 255))))
                pixels[y][x] = (rr, gg, bb) if (rr or gg or bb) else None

        return BitmapFile(width=width, height=height, pixels=pixels, is_monochrome=False)

    @staticmethod
    def _parse_plain_grid(content: str) -> BitmapFile:
        rows: list[list[Color | None]] = []
        width = 0
        is_monochrome = True

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if " " in line or "," in line or ";" in line or "|" in line:
                row = BitmapLoader._parse_color_token_row(line)
            else:
                row = BitmapLoader._parse_bit_row(line)

            if not row:
                continue

            if width == 0:
                width = len(row)
            if len(row) != width:
                raise ValueError("inconsistent bitmap line width")
            if any(px is not None and px != (255, 255, 255) for px in row):
                is_monochrome = False
            rows.append(row)

        if not rows:
            raise ValueError("bitmap file is empty")

        return BitmapFile(width=width, height=len(rows), pixels=rows, is_monochrome=is_monochrome)

    @staticmethod
    def _parse_bit_row(line: str) -> list[Color | None]:
        values: list[Color | None] = []
        for ch in line:
            if ch in {" ", "\t", ",", ";", "|"}:
                continue
            values.append((255, 255, 255) if ch in {"1", "#", "X", "x", "@"} else None)
        return values

    @staticmethod
    def _parse_color_token_row(line: str) -> list[Color | None]:
        row: list[Color | None] = []
        for token in re.split(r"[\s,;|]+", line.strip()):
            if not token:
                continue
            row.append(BitmapLoader._token_to_color(token))
        return row

    @staticmethod
    def _token_to_color(token: str) -> Color | None:
        t = token.strip()
        if not t:
            return None

        lower = t.lower()
        if lower in {"0", ".", "off", "none", "transparent", "-"}:
            return None
        if lower in {"1", "on", "white"}:
            return (255, 255, 255)

        if lower.startswith("#") and len(lower) == 7:
            try:
                return (int(lower[1:3], 16), int(lower[3:5], 16), int(lower[5:7], 16))
            except ValueError:
                return None

        if lower.startswith("0x") and len(lower) == 8:
            try:
                value = int(lower, 16)
                return ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)
            except ValueError:
                return None

        parts = t.split(":")
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            r, g, b = (int(parts[0]), int(parts[1]), int(parts[2]))
            return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))

        return None
