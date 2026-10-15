#!/usr/bin/env python3
"""Build a static, hardware-free Time-Stage gallery outside the source tree."""

import argparse
from datetime import datetime, timedelta
import html
import json
from pathlib import Path
import sys
import time

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.time_stage import NORMAL_SCENES, EVENT_SCENES, catalog, render_scene


def panel(payload, scale=10):
    image = Image.new('RGB', (32 * scale, 8 * scale), '#070b11')
    draw = ImageDraw.Draw(image)
    for y, row in enumerate(payload.color_frame):
        for x, color in enumerate(row):
            draw.rectangle((x * scale, y * scale, (x + 1) * scale - 2, (y + 1) * scale - 2), fill=color or '#101622')
    return image


def build(directory):
    directory.mkdir(parents=True, exist_ok=True)
    cards = []
    sheet = Image.new('RGB', (960, len(NORMAL_SCENES + EVENT_SCENES) * 115), '#090d16')
    draw = ImageDraw.Draw(sheet)
    start = time.perf_counter()
    for row, scene in enumerate(NORMAL_SCENES + EVENT_SCENES):
        special = bool(scene.events)
        base = datetime(2026, 10, 13, 12, 0 if special else 34, 0)
        duration = scene.duration if special else 10
        count = round(duration * 12)
        frames = []
        for i in range(count):
            elapsed = i / 12
            now = base + timedelta(seconds=elapsed * (1 if special else 6))
            frames.append(panel(render_scene(scene.key, now, elapsed)))
        frames[0].save(directory / (scene.key + '.gif'), save_all=True, append_images=frames[1:],
                       duration=[80 if i % 3 else 90 for i in range(count)], loop=0, disposal=2)
        frames[int(count * .8)].save(directory / (scene.key + '.png'))
        draw.text((8, row * 115 + 3), scene.key + ' / ' + scene.title, fill='#e5efff')
        for col, fraction in enumerate((.1, .5, .9)):
            elapsed = duration * fraction
            now = base + timedelta(seconds=elapsed * (1 if special else 6))
            sheet.paste(panel(render_scene(scene.key, now, elapsed), 9), (col * 320, row * 115 + 25))
        kind = 'event' if special else 'normal'
        info = (' · '.join({'hour':'Volle Stunde','half':'Halbe Stunde','quarter':'Viertelstunde'}[e] for e in scene.events)
                if special else 'Sekunden: ' + scene.seconds)
        cards.append(f'<article data-kind="{kind}"><div class="tag">{html.escape(scene.style)}</div><h2>{html.escape(scene.title)}</h2>'
                     f'<img width="320" height="80" loading="lazy" src="{scene.key}.png" data-motion="{scene.key}.gif" data-still="{scene.key}.png" alt="LED-Vorschau: {html.escape(scene.title)}">'
                     f'<p>{html.escape(scene.description)}</p><p class="muted">{html.escape(info)}</p></article>')
    sheet.save(directory / 'contact-sheet.png')
    (directory / 'catalog.json').write_text(json.dumps(catalog(), ensure_ascii=False, indent=2))
    (directory / 'index.html').write_text('''<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Time-Stage · Szenenatelier</title><style>
*{box-sizing:border-box}body{margin:0;background:#090d16;color:#e5efff;font:16px system-ui,sans-serif}header,main{max-width:1150px;margin:auto;padding:24px}
h1{color:#61e5cf}h2{font-size:20px}.muted{color:#b7c5dd}.tag{color:#f4bc67;font-size:12px;text-transform:uppercase}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(320px,100%),1fr));gap:16px}article{padding:16px;background:#131d2d;border:1px solid #33405a;border-radius:12px}
img{width:100%;height:auto;image-rendering:pixelated;background:#070b11}button,a{color:#61e5cf}button{padding:12px;background:#131d2d;border:1px solid #425371;border-radius:6px;cursor:pointer}
button[aria-pressed=true]{border-color:#61e5cf}nav{display:flex;flex-wrap:wrap;gap:10px}[hidden]{display:none!important}
</style><header><a href="/">← PixelDock</a><h1>Time-Stage / Szenenatelier</h1>
<p>25 Uhransichten und 10 magische Momente. Reine Software-Vorschau – ändert weder Playlist noch LED-Anzeige.</p>
<p class="muted">Normale Szenen: eine Minute in 10 Sekunden (6× Zeitraffer). Ereignisse: Echtzeit, wiederholt. Farben sind ungedimmt; die tatsächliche LED-Wirkung hängt von Helligkeit und Hardware ab.</p>
<nav><button data-filter="all" aria-pressed="true">Alle 35</button><button data-filter="normal" aria-pressed="false">25 Uhransichten</button><button data-filter="event" aria-pressed="false">10 Ereignisse</button><button id="pause" aria-pressed="false">Animationen pausieren</button></nav></header><main class="grid">'''
        + ''.join(cards) + '''</main><script>
document.querySelectorAll('[data-filter]').forEach(button=>button.onclick=()=>{
document.querySelectorAll('[data-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
document.querySelectorAll('article').forEach(card=>card.hidden=button.dataset.filter!=='all'&&card.dataset.kind!==button.dataset.filter);});
let paused=matchMedia('(prefers-reduced-motion: reduce)').matches;
function motion(){document.getElementById('pause').setAttribute('aria-pressed',String(paused));document.getElementById('pause').textContent=paused?'Animationen fortsetzen':'Animationen pausieren';
document.querySelectorAll('img').forEach(img=>img.src=paused?img.dataset.still:img.dataset.motion);}
document.getElementById('pause').onclick=()=>{paused=!paused;motion();};motion();
</script></html>''')
    print(f'{len(NORMAL_SCENES + EVENT_SCENES)}-scene gallery built in {time.perf_counter() - start:.2f}s: {directory / "index.html"}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New directory for generated gallery assets')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output directory already exists; use a new versioned path')
    build(args.output)
