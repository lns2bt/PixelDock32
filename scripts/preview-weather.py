#!/usr/bin/env python3
"""Offline Weather-Stage gallery: examples only, never hardware or live data."""
import argparse
from html import escape
import json
from pathlib import Path
import sys
import time
from PIL import Image, ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.weather_stage import Director, STYLES, render, catalog


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    now=time.time()
    cache={'weather_outdoor_temp':12,'weather_indoor_temp':22,'weather_indoor_humidity':48,
           'weather_outdoor_updated_at':now,'weather_outdoor_error':None,'dht_updated_at':now,
           'dht_error':None,'weather_code':61,'weather_is_day':True,'weather_precipitation':1.2,
           'weather_wind_speed':9}
    examples=[(key,{'weather_styles':[key],'weather_max_infos':4}) for key in STYLES]
    for key,code,day in [('sun',0,True),('night',0,False),('clouds',3,True),('rain',61,True),('snow',71,True),('fog',45,True),('storm',95,True)]:
        examples.append((key,{'weather_styles':['home'],'weather_infos':['conditions'], '_code':code,'_day':day}))
    sheet=Image.new('RGB',(512,len(examples)*95),(12,12,18));draw=ImageDraw.Draw(sheet);cards=[]
    for index,(key,options) in enumerate(examples):
        example=dict(cache,weather_code=options.pop('_code',61),weather_is_day=options.pop('_day',True))
        visit=Director().begin(options,example,preview=True)
        frames=[]
        for i in range(max(1,int(visit.duration*10))):
            payload=render(visit,i/10);image=Image.new('RGB',(32,8))
            image.putdata([rgb or (0,0,0) for row in payload.color_frame for rgb in row])
            frames.append(image.resize((256,64),Image.Resampling.NEAREST))
        frames[0].save(args.output/(key+'.gif'),save_all=True,append_images=frames[1:],duration=100,loop=0,optimize=False)
        frames[min(60,len(frames)-1)].save(args.output/(key+'.png'))
        sheet.paste(frames[min(25,len(frames)-1)],(0,index*95+20));sheet.paste(frames[min(60,len(frames)-1)],(256,index*95+20))
        draw.text((0,index*95),key,fill=(100,220,230))
        cards.append(f'<article><h2>{escape(key)}</h2><img src="{key}.gif" data-still="{key}.png" width="256" height="64" alt="{escape(key)} – Beispiel"></article>')
    sheet.save(args.output/'contact-sheet.png');(args.output/'catalog.json').write_text(json.dumps(catalog(),ensure_ascii=False,indent=2))
    (args.output/'index.html').write_text('''<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Wetter-Stage Beispielgalerie</title><style>body{font:16px system-ui;background:#101019;color:#eee;margin:1.5rem}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem}article{padding:1rem;border:1px solid #343440;border-radius:12px}img{width:100%;height:auto;image-rendering:pixelated}a{color:#6ee1ff}h2{font-size:1.2rem}button{padding:.8rem;background:#292936;color:#eee;border:1px solid #555}</style><h1>Wetter-Stage · Beispielgalerie</h1><p>Vier gemeinsame Stile und sieben Wetterbeispiele. Erfundene Werte, keine Live-Daten oder Hardware-Steuerung.</p><p><a href="/weather">Zur Wetter-Stage</a></p><button id="pause">Animationen pausieren</button><main>'''+''.join(cards)+'''</main><script>let stopped=false;const button=document.getElementById('pause');button.onclick=()=>{stopped=!stopped;document.querySelectorAll('img').forEach(img=>{img.dataset.original ||= img.src;img.src=stopped?img.dataset.still:img.dataset.original;});button.textContent=stopped?'Animationen abspielen':'Animationen pausieren';};if(matchMedia('(prefers-reduced-motion: reduce)').matches)button.click();</script></html>''')
    print('Generated',len(examples),'offline weather examples:',args.output)


if __name__=='__main__':main()
