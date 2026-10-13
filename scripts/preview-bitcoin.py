#!/usr/bin/env python3
"""Generate an offline, clearly labelled Bitcoin story gallery (no network IO)."""
import argparse
from html import escape
import json
from pathlib import Path
import sys
from PIL import Image, ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.bitcoin_stage import Director, STYLES, EVENTS, render, catalog


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    cache=dict(btc_eur=65432,btc_block_height=960123,btc_change_24h=2.7,
               btc_updated_at=1000,btc_block_height_updated_at=1000,btc_block_time=580,
               btc_block_details_updated_at=1000,btc_block_details_height=960123,
               btc_fees={'halfHourFee':3},btc_fees_updated_at=1000)
    cards=[];sheet=Image.new('RGB',(512,13*95),(12,12,18));draw=ImageDraw.Draw(sheet)
    for index,(key,(title,description)) in enumerate(list(STYLES.items())+[(f'event_{k}',(v,'Simulierte Neue-Block-Zeremonie')) for k,v in EVENTS.items()]):
        visit=Director().begin({'bitcoin_styles':['forge' if key.startswith('event_') else key]},cache,1000,preview=True)
        if key.startswith('event_'):
            visit.event=key[6:];visit.old_height=960122;visit.new_height=960123
        frames=[]
        for i in range(int(visit.duration*12)):
            payload=render(visit,i/12)
            image=Image.new('RGB',(32,8))
            image.putdata([rgb or (0,0,0) for row in payload.color_frame for rgb in row])
            frames.append(image.resize((256,64),Image.Resampling.NEAREST))
        frames[0].save(args.output/(key+'.gif'),save_all=True,append_images=frames[1:],duration=83,loop=0,optimize=False)
        frames[2].save(args.output/(key+'.png'))
        sheet.paste(frames[2],(0,index*95+20));sheet.paste(frames[min(len(frames)-1,55)],(256,index*95+20))
        draw.text((0,index*95),title,fill=(255,190,75))
        cards.append(f'<article><h2>{escape(title)}</h2><img src="{key}.gif" data-still="{key}.png" width="256" height="64" alt="{escape(title)}"><p>{escape(description)}</p></article>')
    sheet.save(args.output/'contact-sheet.png')
    (args.output/'catalog.json').write_text(json.dumps(catalog(),ensure_ascii=False,indent=2))
    (args.output/'index.html').write_text('''<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Bitcoin-Stage Beispielgalerie</title><style>body{font:16px system-ui;background:#101019;color:#eee;margin:1.5rem}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem}article{padding:1rem;border:1px solid #343440;border-radius:12px}img{width:100%;height:auto;image-rendering:pixelated}a{color:#ffc25c}h2{font-size:1.2rem}button{padding:.8rem;background:#292936;color:#eee;border:1px solid #555}</style><h1>Bitcoin-Stage · Beispielgalerie</h1><p>10 gemeinsame Stile und 3 Neue-Block-Zeremonien. Ausschließlich erfundene Beispielwerte – keine Live-Daten oder Hardware-Steuerung.</p><p><a href="/bitcoin">Zur Bitcoin-Stage</a></p><button id="pause">Animationen pausieren</button><main>'''+''.join(cards)+'''</main><script>let stopped=false;const button=document.getElementById('pause');button.onclick=()=>{stopped=!stopped;document.querySelectorAll('img').forEach(img=>{img.dataset.original ||= img.src;img.src=stopped?img.dataset.still:img.dataset.original;});button.textContent=stopped?'Animationen abspielen':'Animationen pausieren';};if(matchMedia('(prefers-reduced-motion: reduce)').matches)button.click();</script></html>''')
    print('Generated 10 stories and 3 event examples:',args.output)


if __name__=='__main__':main()
