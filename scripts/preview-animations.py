#!/usr/bin/env python3
"""Offline animation + transition gallery (GIFs and a contact sheet).

Renders every animation preset and module transition without hardware.
LED dots are drawn round with a soft halo to approximate the real panel.
"""
import argparse
import asyncio
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.modules.animations import PRESET_INFO, AnimationsModule  # noqa: E402
from app.services import transitions  # noqa: E402
from app.services.rendering import render_text_with_colors  # noqa: E402

SCALE = 10


def led_image(color_frame, scale=SCALE):
    image = Image.new('RGB', (32 * scale, 8 * scale), (8, 8, 12))
    draw = ImageDraw.Draw(image)
    for y, row in enumerate(color_frame):
        for x, rgb in enumerate(row):
            fill = rgb or (22, 22, 28)
            pad = scale * 0.14
            draw.ellipse((x * scale + pad, y * scale + pad, (x + 1) * scale - pad, (y + 1) * scale - pad), fill=fill)
    glow = image.filter(ImageFilter.GaussianBlur(scale * 0.45))
    return Image.blend(image, Image.eval(Image.merge('RGB', [glow.getchannel(i) for i in range(3)]), lambda v: min(255, v * 2)), 0.25)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=6.0)
    parser.add_argument('--fps', type=int, default=20)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    module = AnimationsModule()
    stills = 5
    rows = list(PRESET_INFO)
    sheet = Image.new('RGB', (stills * (32 * 6 + 6), len(rows) * (8 * 6 + 22)), (14, 14, 20))
    draw = ImageDraw.Draw(sheet)

    async def render(preset, t):
        return (await module.render({'preset': preset, 'palette': 'auto', '_elapsed': t}, {})).color_frame

    for index, preset in enumerate(rows):
        frames = []
        total = int(args.seconds * args.fps)
        for i in range(total):
            frames.append(led_image(asyncio.run(render(preset, i / args.fps))))
        frames[0].save(args.output / f'{preset}.gif', save_all=True, append_images=frames[1:],
                       duration=int(1000 / args.fps), loop=0)
        y0 = index * (8 * 6 + 22)
        draw.text((4, y0 + 2), PRESET_INFO[preset][0], fill=(120, 220, 240))
        for s in range(stills):
            frame = asyncio.run(render(preset, 0.7 + s * 1.37))
            sheet.paste(led_image(frame, 6), (s * (32 * 6 + 6), y0 + 16))
    sheet.save(args.output / 'animations-sheet.png')

    old = render_text_with_colors('12:34', base_color=(255, 150, 40))
    new = render_text_with_colors('WX 5C', base_color=(60, 190, 255))
    effects = [key for key in transitions.EFFECTS if key != 'none']
    tsheet = Image.new('RGB', (stills * (32 * 6 + 6), len(effects) * (8 * 6 + 22)), (14, 14, 20))
    tdraw = ImageDraw.Draw(tsheet)
    for index, effect in enumerate(effects):
        frames = [led_image(transitions.render(effect, *old, *new, i / 23)[1]) for i in range(24)]
        frames = frames + [frames[-1]] * 8 + [frames[0]] * 8
        frames[0].save(args.output / f'transition-{effect}.gif', save_all=True, append_images=frames[1:],
                       duration=40, loop=0)
        y0 = index * (8 * 6 + 22)
        tdraw.text((4, y0 + 2), transitions.EFFECTS[effect], fill=(120, 220, 240))
        for s in range(stills):
            tsheet.paste(led_image(transitions.render(effect, *old, *new, (s + 0.5) / stills)[1], 6),
                         (s * (32 * 6 + 6), y0 + 16))
    tsheet.save(args.output / 'transitions-sheet.png')
    print('Generated', len(rows), 'animations and', len(effects), 'transitions in', args.output)


if __name__ == '__main__':
    main()
