from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from app.services.assets import MAX_FRAMES, MAX_ASSET_BYTES, AssetStore, asset_frame, decode_image, validate_asset
from app.services.retro_scenes import seed_retro_assets


class AssetTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = AssetStore(directory.name)

    def test_sprite_roundtrip_timing_and_rgb(self):
        pixels = [0x123456] + [0] * 255
        saved = self.store.save({"name": "Test", "frames": [{"pixels": pixels, "duration_ms": 100}, {"pixels": [0xabcdef] * 256, "duration_ms": 200}]})
        data = self.store.load(saved["id"])
        self.assertEqual(data["cycle_seconds"], .3)
        self.assertEqual(asset_frame(data, .05)[1][0][0], (0x12, 0x34, 0x56))
        self.assertEqual(asset_frame(data, .15)[1][0][0], (0xab, 0xcd, 0xef))
        self.assertEqual(len(self.store.list()), 1)
        self.store.delete(saved["id"])
        self.assertEqual(self.store.list(), [])

    def test_path_traversal_and_invalid_pixels_rejected(self):
        for asset_id in ("../secret", "/etc/passwd", "a/b", None):
            with self.assertRaises(ValueError):
                self.store.load(asset_id)
        for value in (-1, 0x1000000, True, "ffffff"):
            with self.assertRaises(ValueError):
                validate_asset({"name": "Test", "frames": [{"pixels": [value] * 256, "duration_ms": 100}]})

    def test_frame_count_and_duration_are_bounded(self):
        for duration in (0, 32, 2001, float('inf')):
            with self.assertRaises(ValueError):
                validate_asset({"name": "Test", "frames": [{"pixels": [0] * 256, "duration_ms": duration}]})
        with self.assertRaises(ValueError):
            validate_asset({"name": "Test", "frames": [{"pixels": [0] * 256, "duration_ms": 100}] * (MAX_FRAMES + 1)})

    def test_maximum_length_bright_asset_can_be_saved_loaded_and_listed(self):
        data = {"name": "Long animation", "frames": [{"pixels": [0xffffff] * 256, "duration_ms": 2000}] * MAX_FRAMES}
        saved = self.store.save(data)
        self.assertGreater(self.store.path(saved['id']).stat().st_size, 512_000)
        self.assertLess(self.store.path(saved['id']).stat().st_size, MAX_ASSET_BYTES)
        loaded = self.store.load(saved['id'])
        self.assertEqual(len(loaded['frames']), MAX_FRAMES)
        self.assertEqual(len(self.store.list()), 1)
        self.assertEqual(asset_frame(loaded, 1000)[1][0][0], (255, 255, 255))

    def test_267_frame_gif_import_roundtrip_preserves_timing_and_all_frames(self):
        buffer = BytesIO()
        frames = [Image.new('RGB', (32, 8), 'red' if i % 2 else 'blue') for i in range(267)]
        durations = [100 if i % 2 else 200 for i in range(267)]
        frames[0].save(buffer, format='GIF', save_all=True, append_images=frames[1:], duration=durations)
        decoded = decode_image(buffer.getvalue(), '267 frames', 'contain')
        saved = self.store.save(decoded)
        loaded = self.store.load(saved['id'])
        self.assertEqual(len(loaded['frames']), 267)
        self.assertEqual([f['duration_ms'] for f in loaded['frames']], durations)
        self.assertEqual(loaded['frames'][-1]['pixels'][0], 0x0000ff)
        self.assertEqual(self.store.list()[0]['frame_count'], 267)

    def test_gif_import_retains_frames_and_timing(self):
        buffer = BytesIO()
        Image.new("RGB", (32, 8), "red").save(buffer, format="GIF", save_all=True, append_images=[Image.new("RGB", (32, 8), "blue")], duration=[100, 200], loop=0)
        asset = decode_image(buffer.getvalue(), "GIF", "contain")
        self.assertEqual([f["duration_ms"] for f in asset["frames"]], [100, 200])
        self.assertEqual(asset["frames"][0]["pixels"][0], 0xff0000)
        self.assertEqual(asset["frames"][1]["pixels"][0], 0x0000ff)

    def test_png_transparency_and_fit_modes(self):
        buffer = BytesIO()
        image = Image.new("RGBA", (8, 8), (255, 0, 0, 0))
        image.putpixel((4, 4), (0, 255, 0, 255))
        image.save(buffer, format="PNG")
        for fit in ("contain", "cover", "stretch"):
            asset = decode_image(buffer.getvalue(), "PNG", fit)
            self.assertEqual(len(asset["frames"][0]["pixels"]), 256)
            self.assertIn(0x00ff00, asset["frames"][0]["pixels"])
            self.assertNotIn(0xff0000, asset["frames"][0]["pixels"])

    def test_large_dimensions_and_unsupported_images_rejected(self):
        buffer = BytesIO()
        Image.new("RGB", (1025, 1)).save(buffer, format="PNG")
        with self.assertRaises(ValueError):
            decode_image(buffer.getvalue(), "Large", "contain")
        buffer = BytesIO()
        Image.new("RGB", (32, 8)).save(buffer, format="JPEG")
        with self.assertRaises(ValueError):
            decode_image(buffer.getvalue(), "Unsupported", "contain")

    def test_gif_frame_limit_stops_without_scanning_unlimited_frames(self):
        buffer = BytesIO()
        frames = [Image.new("RGB", (1, 1), "red" if i % 2 else "blue") for i in range(MAX_FRAMES + 1)]
        frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=100)
        with self.assertRaisesRegex(ValueError, f"maximal {MAX_FRAMES}"):
            decode_image(buffer.getvalue(), "Too many", "contain")

    def test_total_source_pixel_budget_has_distinct_error(self):
        buffer = BytesIO()
        frames = [Image.new('RGB', (512, 512), 'red' if i % 2 else 'blue') for i in range(31)]
        frames[0].save(buffer, format='GIF', save_all=True, append_images=frames[1:], duration=100)
        with self.assertRaisesRegex(ValueError, '8 Millionen Quellpixel'):
            decode_image(buffer.getvalue(), 'Large resolution', 'contain')

    def test_original_demos_seed_once_and_render(self):
        seed_retro_assets(self.store)
        seed_retro_assets(self.store)
        self.assertEqual(len(self.store.list()), 3)
        for asset in self.store.list():
            data = self.store.load(asset["id"])
            self.assertEqual(len(data["frames"]), 32)
            self.assertNotEqual(data["frames"][0]["pixels"], data["frames"][1]["pixels"])
