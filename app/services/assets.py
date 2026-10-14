"""Bounded, predecoded 32x8 assets. No image decoding in the rendering loop."""

from collections import OrderedDict
from io import BytesIO
import json
import math
from pathlib import Path
import re
import threading
import uuid
import warnings
from app.services.asset_editing import MAX_SOURCE_FRAMES, selection_plan

from PIL import Image, ImageOps

MAX_UPLOAD = 4 * 1024 * 1024
MAX_FRAMES = 512
MAX_ASSET_BYTES = 2 * 1024 * 1024
MAX_ASSETS = 128
ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def validate_asset(data):
    frames = data.get("frames")
    if not isinstance(frames, list) or not 1 <= len(frames) <= MAX_FRAMES:
        raise ValueError(f"1–{MAX_FRAMES} Frames erforderlich")
    for frame in frames:
        if not isinstance(frame, dict):
            raise ValueError("Ungültiger Frame")
        pixels = frame.get("pixels")
        if not isinstance(pixels, list) or len(pixels) != 256 or any(type(p) is not int or not 0 <= p <= 0xFFFFFF for p in pixels):
            raise ValueError("Jeder Frame benötigt 256 RGB-Pixel")
        duration = frame.get("duration_ms")
        if type(duration) is not int or not 33 <= duration <= 2000:
            raise ValueError("Frame-Dauer muss 33–2000 ms sein")
    name = data.get("name", "Pixel-Animation")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise ValueError("Name muss 1–80 Zeichen haben")
    return {"name": name.strip(), "frames": frames}


def _open_image(raw):
    if len(raw) > MAX_UPLOAD:
        raise ValueError("Maximal 4 MB pro Upload")
    image = Image.open(BytesIO(raw))
    if image.format not in {'GIF','PNG'}:
        image.close();raise ValueError('Nur GIF und PNG werden unterstützt')
    if image.width > 1024 or image.height > 1024 or image.width * image.height > 262144:
        image.close();raise ValueError('Bild zu groß: maximal 1024 je Seite und 262144 Pixel')
    return image


def analyze_image(raw):
    """Only durations/geometry; do not allocate an unbounded decoded animation."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with _open_image(raw) as image:
            durations=[];width,height=image.size
            for index in range(MAX_SOURCE_FRAMES+1):
                try:
                    image.seek(index)
                except EOFError:
                    break
                if index == MAX_SOURCE_FRAMES:
                    raise ValueError('Zu viele Quellframes: maximal 4096 für die Importvorbereitung')
                if image.width * image.height * (index + 1) > 8_000_000:
                    raise ValueError("Animation-Auflösung zu groß: maximal 8 Millionen Quellpixel über alle Frames. Bitte vor dem Import auf 32 × 8 verkleinern.")
                durations.append(max(33,min(655350,int(image.info.get('duration',100) or 100))))
            return {'frame_count':len(durations),'durations_ms':durations,'width':width,'height':height,
                    'cycle_seconds':sum(durations)/1000,'bytes':len(raw),'max_frames':MAX_FRAMES}


def decode_image(raw, name, fit, **options):
    if fit not in {'contain','cover','stretch'}: raise ValueError('Ungültige Skalierung')
    analysis=analyze_image(raw)
    plan=selection_plan(analysis['durations_ms'],**options)
    if plan['frame_count']>MAX_FRAMES:
        raise ValueError(f'Zu viele Frames: maximal {MAX_FRAMES} im fertigen Asset. Bitte Bereich kürzen oder Frames ausdünnen.')
    frames=[]
    with warnings.catch_warnings():
        warnings.simplefilter('error',Image.DecompressionBombWarning)
        with _open_image(raw) as image:
            previous_index=None; pixels=None
            for group in plan['groups']:
                index=group['index']
                if index==previous_index:
                    frames.append({'pixels':pixels,'duration_ms':group['duration_ms']});continue
                image.seek(index)
                rgba = image.convert("RGBA")
                if fit == "cover":
                    rgba = ImageOps.fit(rgba, (32, 8), method=Image.Resampling.NEAREST)
                elif fit == "stretch":
                    rgba = rgba.resize((32, 8), Image.Resampling.NEAREST)
                else:
                    rgba = ImageOps.contain(rgba, (32, 8), method=Image.Resampling.NEAREST)
                    canvas = Image.new("RGBA", (32, 8))
                    canvas.paste(rgba, ((32 - rgba.width) // 2, (8 - rgba.height) // 2))
                    rgba = canvas
                black = Image.new("RGB", (32, 8))
                black.paste(rgba, mask=rgba.getchannel("A"))
                pixels = [(r << 16) | (g << 8) | b for r, g, b in black.get_flattened_data()]
                frames.append({"pixels": pixels, "duration_ms": group['duration_ms']})
                previous_index=index
    return validate_asset({"name": name, "frames": frames})


class AssetStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._cache = OrderedDict()
        self._lock = threading.RLock()

    def path(self, asset_id):
        if not isinstance(asset_id, str) or not ID_PATTERN.fullmatch(asset_id):
            raise ValueError("Ungültige Asset-ID")
        return self.directory / (asset_id + ".json")

    def save(self, data):
        data = validate_asset(data)
        with self._lock:
            if len(list(self.directory.glob("*.json"))) >= MAX_ASSETS:
                raise ValueError("Bibliothek voll (128 Assets)")
            asset_id = uuid.uuid4().hex
            path = self.path(asset_id)
            with path.open("x", encoding="utf-8") as handle:
                json.dump(data, handle, separators=(",", ":"))
            return {"id": asset_id, **data}

    def load(self, asset_id):
        with self._lock:
            if asset_id not in self._cache:
                path = self.path(asset_id)
                if path.stat().st_size > MAX_ASSET_BYTES:
                    raise ValueError("Asset-Datei zu groß")
                data = validate_asset(json.loads(path.read_text()))
                data["id"] = asset_id
                data["cycle_seconds"] = sum(f["duration_ms"] for f in data["frames"]) / 1000
                self._cache[asset_id] = data
                if len(self._cache) > 8:
                    self._cache.popitem(last=False)
            self._cache.move_to_end(asset_id)
            return self._cache[asset_id]

    def list(self):
        result = []
        for path in sorted(self.directory.glob("*.json"))[:MAX_ASSETS]:
            try:
                data = self.load(path.stem)
                result.append({"id": path.stem, "name": data["name"], "frame_count": len(data["frames"]),
                               "cycle_seconds": data["cycle_seconds"], "width":32,"height":8,
                               "preview": data["frames"][0]["pixels"]})
            except (ValueError, OSError):
                continue
        return result

    def delete(self, asset_id):
        with self._lock:
            self.path(asset_id).unlink()
            self._cache.pop(asset_id, None)


def asset_frame(data, elapsed, speed=1.0):
    speed = float(speed)
    if not math.isfinite(speed) or not 0.1 <= speed <= 4:
        speed = 1.0
    position = (max(0, elapsed) * speed * 1000) % (data["cycle_seconds"] * 1000)
    selected = data["frames"][-1]
    for candidate in data["frames"]:
        if position < candidate["duration_ms"]:
            selected = candidate
            break
        position -= candidate["duration_ms"]
    colors = [[None for _ in range(32)] for _ in range(8)]
    frame = [[0 for _ in range(32)] for _ in range(8)]
    for i, value in enumerate(selected["pixels"]):
        if value:
            y, x = divmod(i, 32)
            frame[y][x] = 1
            colors[y][x] = (value >> 16, (value >> 8) & 255, value & 255)
    return frame, colors
