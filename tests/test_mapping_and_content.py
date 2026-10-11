import asyncio
from pathlib import Path
import tempfile
import unittest

from app.config import Settings
from app.modules.animations import AnimationsModule, PALETTES, PRESETS
from app.services.bitmap_loader import BitmapLoader
from app.services.led_mapper import LEDMapper
from scripts_verify_glyphs import main as verify_glyphs


class MappingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.state = Path(directory.name) / "mapping.json"
        self.settings = Settings(_env_file=None, mapping_state_file=str(self.state))
        self.mapper = LEDMapper(self.settings)

    def test_default_is_bijection(self):
        indices = [self.mapper.xy_to_index(x, y) for y in range(8) for x in range(32)]
        self.assertEqual(sorted(indices), list(range(256)))
        self.assertEqual(self.mapper.xy_to_index(0, 0), 192)
        self.assertEqual(self.mapper.xy_to_index(0, 1), 207)

    def test_rotations_and_order_preserve_bijection(self):
        for rotation in (0, 90, 180, 270):
            self.mapper.apply_runtime_overrides(first_pixel_offset=0, data_starts_right=False, serpentine=True, panel_order=[3, 2, 1, 0], panel_rotations=[rotation] * 4)
            indices = [self.mapper.xy_to_index(x, y) for y in range(8) for x in range(32)]
            self.assertEqual(sorted(indices), list(range(256)))

    def test_mapping_and_pixel_fix_persist(self):
        self.mapper.apply_runtime_overrides(first_pixel_offset=0, data_starts_right=False, serpentine=False, panel_order=[0, 1, 2, 3], panel_rotations=[0, 0, 0, 0])
        self.mapper.set_pixel_fix(logical_x=0, logical_y=0, observed_x=1, observed_y=0)
        restored = LEDMapper(self.settings)
        self.assertEqual(restored.xy_to_index(0, 0), 1)
        self.assertEqual(len(restored.get_pixel_fixes_snapshot()), 1)

    def test_invalid_coordinates_and_order(self):
        for x, y in ((-1, 0), (32, 0), (0, 8)):
            with self.assertRaises(ValueError):
                self.mapper.xy_to_index(x, y)
        with self.assertRaises(ValueError):
            self.mapper.apply_runtime_overrides(first_pixel_offset=0, data_starts_right=True, serpentine=True, panel_order=[0, 0, 2, 3], panel_rotations=[0] * 4)


class ContentTests(unittest.TestCase):
    def test_glyph_regressions(self):
        verify_glyphs()

    def test_animation_shapes_and_channels(self):
        async def check():
            module = AnimationsModule()
            for preset in sorted(PRESETS):
                for palette in PALETTES:
                    for mirror in ("none", "horizontal", "vertical", "quad"):
                        payload = await module.render({"preset": preset, "palette": palette, "mirror_mode": mirror}, {})
                        self.assertEqual(len(payload.frame), 8)
                        self.assertEqual(len(payload.color_frame), 8)
                        for row, colors in zip(payload.frame, payload.color_frame):
                            self.assertEqual(len(row), 32)
                            self.assertEqual(len(colors), 32)
                            for on, rgb in zip(row, colors):
                                self.assertIn(on, (0, 1))
                                if on:
                                    self.assertIsNotNone(rgb)
                                if rgb is not None:
                                    self.assertEqual(len(rgb), 3)
                                    self.assertTrue(all(isinstance(c, int) and 0 <= c <= 255 for c in rgb))
        asyncio.run(check())

    def test_sample_bitmap_and_cache(self):
        loader = BitmapLoader(Path("app/bitmaps"))
        bitmap = loader.load("sample_gradient.ppm")
        self.assertIs(loader.load("sample_gradient.ppm"), bitmap)
        frame, colors = loader.render_window(bitmap, "top_to_bottom", 2, now=1)
        self.assertEqual(len(frame), 8)
        self.assertTrue(all(len(row) == 32 for row in colors))

    def test_bitmap_path_cannot_escape_assets(self):
        loader = BitmapLoader(Path("app/bitmaps"))
        with self.assertRaises(ValueError):
            loader.load("../../README.md")
