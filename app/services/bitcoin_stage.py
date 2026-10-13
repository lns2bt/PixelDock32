"""Bitcoin's equal-weight information rotation and pure 32×8 story renderer.

No IO in rendering. Visits freeze their data and finish each reading phase.
"""
from copy import deepcopy
from dataclasses import dataclass
import math
import random
import time

from app.modules.base import ModulePayload
from app.services.time_stage.core import Canvas, shade


INFOS = {
    'price': ('Preis EUR', 'EUR'), 'height': ('Blockhöhe', 'BLOCK'),
    'sats': ('Sats pro Euro', 'SAT/EUR'), 'age': ('Alter des letzten Blocks', 'ALTER'),
    'fees': ('Gebührenempfehlung', 'SAT/VB'), 'halving': ('Blöcke bis zum Halving', 'HALVING'),
    'change': ('Preisänderung 24h', '24H %'),
}
STYLES = {
    'forge': ('Block-Schmiede', 'Glut, Hammer und goldene Funken'),
    'train': ('Blockchain-Zug', 'Verkettete Wagen bringen die nächste Information'),
    'mine': ('Mining-Schacht', 'Spitzhacke und Goldadern im dunklen Gestein'),
    'nonce': ('Nonce-Suche', 'Künstlerischer Zahlensuchlauf, kein echtes Mining'),
    'orbit': ('Bitcoin-Orbit', 'Satelliten umkreisen einen orangefarbenen Block'),
    'rain': ('Transaktionsregen', 'Symbolische Transaktionen sammeln sich; keine Mempoolmessung'),
    'terminal': ('Cyber-Terminal', 'Scanlinien und grün-orange Datentelegramme'),
    'counter': ('Mechanischer Zähler', 'Zahnräder und präzise rollende Ziffern'),
    'tetris': ('Block-Tetris', 'Fallende Steine setzen sich zu einem Block zusammen'),
    'vein': ('Goldader', 'Licht wandert durch eine leuchtende Erzader'),
}
EVENTS = {'dock': 'Neuer Block dockt an', 'forge': 'Neuer Block wird geschmiedet', 'counter': 'Höhenzähler wechselt'}
DEFAULTS = dict(bitcoin_stage=True, bitcoin_infos=list(INFOS), bitcoin_max_infos=2,
                bitcoin_info_order='ordered', bitcoin_styles=list(STYLES),
                bitcoin_style_order='ordered', bitcoin_read_seconds=4,
                bitcoin_intensity='normal', bitcoin_events=True,
                bitcoin_event_styles=list(EVENTS), bitcoin_fee_level='halfHourFee')
ORANGE = (255, 130, 12)
GOLD = (255, 207, 80)


def normalize(settings):
    result = {**DEFAULTS, **(settings or {})}
    for key, allowed in [('bitcoin_infos', INFOS), ('bitcoin_styles', STYLES), ('bitcoin_event_styles', EVENTS)]:
        value = result[key]
        result[key] = list(dict.fromkeys(item for item in value if isinstance(item, str) and item in allowed)) if isinstance(value, list) else []
        if not result[key]: result[key] = list(allowed)
    for key, low, high in [('bitcoin_max_infos', 1, 7), ('bitcoin_read_seconds', 2, 15)]:
        try: result[key] = max(low, min(high, int(result[key])))
        except (TypeError, ValueError, OverflowError): result[key] = DEFAULTS[key]
    for key in ('bitcoin_info_order', 'bitcoin_style_order'):
        if result[key] not in ('ordered', 'random'): result[key] = 'ordered'
    if result['bitcoin_intensity'] not in ('calm', 'normal', 'lively'): result['bitcoin_intensity'] = 'normal'
    if result['bitcoin_fee_level'] not in ('economyFee', 'hourFee', 'halfHourFee', 'fastestFee'): result['bitcoin_fee_level'] = 'halfHourFee'
    for key in ('bitcoin_stage', 'bitcoin_events'): result[key] = bool(result[key])
    return result


def number(value, low=0):
    if isinstance(value, bool): return None
    try: parsed = float(value)
    except (ValueError, TypeError, OverflowError): return None
    return parsed if math.isfinite(parsed) and parsed >= low else None


def info_value(key, cache, settings, now=None):
    now = time.time() if now is None else now
    price = number(cache.get('btc_eur'), .000001)
    height = number(cache.get('btc_block_height'))
    if height is not None and height != int(height): height = None
    stamp = cache.get('btc_updated_at') if key in ('price', 'sats', 'change') else cache.get('btc_block_height_updated_at')
    error = cache.get('btc_error') if key in ('price', 'sats', 'change') else cache.get('btc_block_height_error')
    value = None
    if key == 'price' and price is not None:
        value = f'{price / 1_000_000:.2f}M' if price >= 1_000_000 else f'{price / 1000:.1f}K' if price >= 10000 else str(round(price))
    elif key == 'height' and height is not None: value = str(int(height))
    elif key == 'sats' and price is not None:
        sats = 100_000_000 / price
        value = str(round(sats)) if sats < 1_000_000 else f'{sats / 1_000_000:.1f}M'
    elif key == 'halving' and height is not None:
        value = str((int(height) // 210_000 + 1) * 210_000 - int(height)) if height < 6_930_000 else 'ENDE'
    elif key == 'age':
        block_time = number(cache.get('btc_block_time'))
        stamp = cache.get('btc_block_details_updated_at'); error = cache.get('btc_block_details_error')
        if block_time is not None and block_time <= now and cache.get('btc_block_details_height', height) == height:
            minutes = int((now - block_time) / 60)
            value = f'{minutes}MIN' if minutes < 1000 else f'{minutes // 60}STD'
    elif key == 'fees':
        fees = cache.get('btc_fees')
        fee = number(fees.get(settings['bitcoin_fee_level'])) if isinstance(fees,dict) else None
        stamp = cache.get('btc_fees_updated_at'); error = cache.get('btc_fees_error')
        if fee is not None: value = f'{fee:.1f}'.rstrip('0').rstrip('.')
    elif key == 'change':
        change = number(cache.get('btc_change_24h'), -100)
        if change is not None: value = f'{change:+.1f}%'
    fresh_stamp = number(stamp)
    if value is not None and len(value)>24: value = None
    stale = value is not None and (bool(error) or fresh_stamp is None or now - fresh_stamp > 300 or fresh_stamp > now + 60)
    return {'key': key, 'title': INFOS[key][0], 'label': INFOS[key][1],
            'value': value or '--', 'state': 'missing' if value is None else 'stale' if stale else 'fresh',
            'updated_at': stamp}


class FairRotation:
    """A complete pass before another pass; random uses a shuffled bag."""
    def __init__(self, rng):
        self.rng = rng; self.signature = None; self.bag = []; self.last = None

    def take(self, keys, count, mode):
        signature = (tuple(keys), mode)
        if signature != self.signature: self.signature = signature; self.bag = []
        chosen = []
        while len(chosen) < min(count, len(keys)):
            if not self.bag:
                self.bag = list(keys)
                if mode == 'random':
                    self.rng.shuffle(self.bag)
                    if len(self.bag) > 1 and self.bag[0] == self.last: self.bag[0], self.bag[-1] = self.bag[-1], self.bag[0]
            index = next((i for i, key in enumerate(self.bag) if key not in chosen), None)
            if index is None: break  # Maximum is a ceiling, not an obligation.
            key = self.bag.pop(index); chosen.append(key); self.last = key
        return chosen


@dataclass
class Visit:
    style: str
    infos: list
    settings: dict
    event: str | None = None
    old_height: int | None = None
    new_height: int | None = None

    @property
    def read_seconds(self):
        scrolling = max(((len(info['value'])*4+32)/12 for info in self.infos if len(info['value'])>8),default=0)
        return max(self.settings['bitcoin_read_seconds'],scrolling)

    @property
    def segment(self): return 4 + self.read_seconds

    @property
    def duration(self): return (6 if self.event else 0) + .8 + len(self.infos) * self.segment + .6


def presentation_timing(settings, cache=None, now=None):
    """Estimate a visit without consuming rotation or adding playlist minimums.

    The configured selection's first capped batch matches preview semantics.
    Without cached values this is the ordinary-value metadata estimate; cached
    values extend reading exactly as Visit does for a complete scroll.
    """
    settings = normalize(settings)
    now = time.time() if now is None else now
    keys = settings['bitcoin_infos'][:settings['bitcoin_max_infos']]
    visit = Visit(settings['bitcoin_styles'][0],
                  [info_value(key, cache if cache is not None else {}, settings, now) for key in keys],
                  settings)
    return {'duration': float(visit.duration), 'info_count': len(visit.infos),
            'read_seconds': float(visit.read_seconds), 'event_extra_seconds': 6,
            'automatic': settings['bitcoin_stage']}


class Director:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.infos = FairRotation(self.rng); self.styles = FairRotation(self.rng); self.events = FairRotation(self.rng)
        self.height = None; self.height_stamp = None; self.pending = None

    def observe(self, cache, now, sleeping=False):
        value = number(cache.get('btc_block_height'))
        if value is None or value != int(value):
            if sleeping: self.pending = None
            return
        value = int(value)
        stamp = number(cache.get('btc_block_height_updated_at'))
        recent_baseline = self.height_stamp is not None and 0 <= now-self.height_stamp <= 300
        if not sleeping and recent_baseline and not cache.get('btc_block_height_error') and self.height is not None and value == self.height + 1 and stamp is not None and 0 <= now - stamp <= 120:
            self.pending = (self.height, value, now)
        elif self.height is not None and value != self.height:
            self.pending = None
        self.height = value
        self.height_stamp = stamp
        if sleeping or cache.get('btc_block_height_error') or self.pending and not 0 <= now - self.pending[2] <= 120: self.pending = None

    def begin(self, settings, cache, now=None, preview=False):
        settings = normalize(settings); now = time.time() if now is None else now
        if preview:
            keys = settings['bitcoin_infos'][:settings['bitcoin_max_infos']]; style = settings['bitcoin_styles'][0]
        else:
            keys = self.infos.take(settings['bitcoin_infos'], settings['bitcoin_max_infos'], settings['bitcoin_info_order'])
            style = self.styles.take(settings['bitcoin_styles'], 1, settings['bitcoin_style_order'])[0]
        event = old = new = None
        if not preview and self.pending and settings['bitcoin_events'] and now - self.pending[2] <= 120:
            old, new, _ = self.pending
            event = self.events.take(settings['bitcoin_event_styles'], 1, 'ordered')[0]
        if not preview: self.pending = None
        return Visit(style, [info_value(key, cache, settings, now) for key in keys], deepcopy(settings), event, old, new)


def line(canvas, x1, y1, x2, y2, color):
    steps = max(abs(int(x2-x1)), abs(int(y2-y1)), 1)
    for i in range(steps+1): canvas.pixel(x1+(x2-x1)*i/steps, y1+(y2-y1)*i/steps, color)


def box(canvas, x, y, w, h, color, fill=False):
    for dy in range(h):
        for dx in range(w):
            if fill or dx in (0,w-1) or dy in (0,h-1): canvas.pixel(x+dx,y+dy,color)


def story(style, elapsed, info='height', intensity='normal'):
    """Distinct motifs, sharing Bitcoin gold and a bounded deterministic timeline."""
    canvas = Canvas()
    t = elapsed * {'calm':.55,'normal':1,'lively':1.4}[intensity]
    accent = {'price':GOLD,'height':ORANGE,'sats':(255,235,120),'age':(110,205,240),
              'fees':(155,220,100),'halving':(230,145,255),'change':(130,225,180)}[info]
    if style == 'forge':
        box(canvas,10,4,12,3,shade(ORANGE,.4),True); box(canvas,13,2,6,3,accent,True)
        y = 0 if int(t*4)%4 < 2 else 2
        line(canvas,21,y,25,y, GOLD); line(canvas,23,y,26,0,ORANGE)
        for i in range(9):
            phase=(t*1.8+i*.13)%1;canvas.pixel(16+(i-4)*phase*3,3-phase*4,shade(GOLD,1-phase))
    elif style == 'train':
        for x in range(32): canvas.pixel(x,7,shade(ORANGE,.3))
        shift=int(t*8)%12
        for i in range(4):
            x=i*12-shift;box(canvas,x,2,9,4,accent);line(canvas,x+9,4,x+12,4,ORANGE)
            canvas.pixel(x+2,6,GOLD);canvas.pixel(x+6,6,GOLD)
    elif style == 'mine':
        for x in range(32):
            canvas.pixel(x,7-(x*7%3),shade(ORANGE,.18))
            if (x+int(t*5))%7<2:canvas.pixel(x,5-(x%3),GOLD)
        swing=math.sin(t*5)
        line(canvas,15,4,20+swing*2,1,ORANGE);line(canvas,17+swing*2,1,23+swing*2,2,GOLD)
        for i in range(5):canvas.pixel(14-i*(t%1),4+i%3,shade(accent,1-t%1))
    elif style == 'nonce':
        digits=''.join(str((int(t*18)+i*i*13)%10) for i in range(8))
        canvas.text(digits,0,1,shade(accent,.8));canvas.pixel(int(t*12)%32,7,GOLD)
    elif style == 'orbit':
        box(canvas,13,2,6,4,accent)
        for i in range(4):
            angle=t*1.8+i*math.pi/2
            canvas.pixel(16+14*math.cos(angle),3.5+3.4*math.sin(angle),GOLD)
            canvas.pixel(16+12*math.cos(angle-.1),3.5+2.8*math.sin(angle-.1),shade(ORANGE,.4))
    elif style == 'rain':
        box(canvas,12,2,8,6,accent)
        for i in range(12):
            x=(i*11)%32; y=(t*(3+i%3)+i*3)%8
            canvas.pixel(x,y,GOLD);canvas.pixel(x,y-1,shade(ORANGE,.3))
        for x in range(14,18):canvas.pixel(x,6-int(t)%3,GOLD)
    elif style == 'terminal':
        for i in range(14):canvas.pixel((i*13)%32,(i*7+int(t*6))%8,(20,90,40))
        canvas.text('> BTC',3,1,accent)
        for y in range(8):canvas.pixel(int(t*18)%32,y,(110,255,125))
    elif style == 'counter':
        for cx in (4,27):
            for i in range(8):
                a=t*2+i*math.pi/4;canvas.pixel(cx+3*math.cos(a),3+3*math.sin(a),ORANGE)
            canvas.pixel(cx,3,GOLD)
        box(canvas,10,0,12,8,shade(ORANGE,.4));canvas.text(str(int(t*10)%100).zfill(2),12,1,accent)
    elif style == 'tetris':
        for i in range(7):
            x=i*4+1;y=min(5-i%2,int((t+i*.3)%2*7)-3)
            box(canvas,x,y,3,3,accent if i%2 else ORANGE,True)
        for x in range(32):canvas.pixel(x,7,shade(GOLD,.35))
    elif style == 'vein':
        for x in range(32):
            y=3+int(2*math.sin(x*.5));distance=(x-int(t*12))%32
            canvas.pixel(x,y,shade(accent,1-distance/34));canvas.pixel(x,y+1,shade(ORANGE,.18))
        box(canvas,13,1,6,6,shade(GOLD,.35))
    # Each metric has its own emblem, interpreted in the same story palette.
    emblems = {'price':['010','111','110','111','010'], 'height':['111','101','111'],
               'sats':['010','111','010'], 'age':['111','010','111'],
               'fees':['101','101','101'], 'halving':['101','000','101'],
               'change':['001','011','101']}
    if style not in ('nonce','terminal'):
        canvas.bitmap(emblems[info],15,1 if info=='price' else 2,accent)
    return canvas


def text(canvas, value, elapsed, color, offset_y=0):
    # All normal metrics fit eight 3×5 glyphs. Truly large values scroll completely.
    width = len(value)*4-1
    x = (32-width)//2 if width <= 32 else 32-int(elapsed*12)
    canvas.text(value,x,1+offset_y,color)


def render(visit, elapsed):
    elapsed=max(0,float(elapsed))
    canvas=Canvas(); message=''; key='bitcoin:'+visit.style
    if visit.event and elapsed < 6:
        event=visit.event
        if elapsed < 2:
            canvas=story('train' if event=='dock' else 'forge' if event=='forge' else 'counter',elapsed,'height',visit.settings['bitcoin_intensity'])
        elif elapsed < 3: text(canvas,'NEU',elapsed,ORANGE)
        else:
            message=str(visit.new_height)
            if event=='counter' and elapsed < 3.5:
                text(canvas,str(visit.old_height),elapsed,GOLD,offset_y=-int((elapsed-3)*14))
                text(canvas,message,elapsed,ORANGE,offset_y=7-int((elapsed-3)*14))
            else: text(canvas,message,elapsed,ORANGE)
        key+=':new-block'; message=message or 'NEUER BLOCK'
    else:
        elapsed-=6 if visit.event else 0
        if elapsed < .8:
            canvas=story(visit.style,elapsed,visit.infos[0]['key'],visit.settings['bitcoin_intensity'])
        else:
            index=min(len(visit.infos)-1,int((elapsed-.8)/visit.segment))
            info=visit.infos[index]; phase=(elapsed-.8)-index*visit.segment
            message=info['label']+' '+info['value'];key+=':'+info['key']
            color = (130,130,140) if info['state']=='missing' else GOLD
            if info['key']=='change' and info['state']!='missing':color=(90,235,130) if info['value'].startswith('+') else (255,90,70)
            if phase < .9:
                text(canvas,info['label'],phase,ORANGE)
            elif phase < 2.2:
                canvas=story(visit.style,phase,info['key'],visit.settings['bitcoin_intensity'])
            elif phase < 2.9:
                motif=story(visit.style,phase,info['key'],visit.settings['bitcoin_intensity'])
                target=Canvas();text(target,info['value'],phase,color)
                progress=(phase-2.2)/.7
                for y in range(8):
                    for x in range(32):
                        if visit.style in ('train','terminal','vein'): revealed=x/32<progress
                        elif visit.style in ('mine','rain','tetris'): revealed=y/8<progress
                        elif visit.style=='counter': revealed=y/8>1-progress
                        elif visit.style=='orbit': revealed=abs(x-16)/16<progress
                        else: revealed=(x*7+y*11)%31/31<progress
                        rgb=target.colors[y][x] if revealed else motif.colors[y][x]
                        if rgb:canvas.pixel(x,y,rgb)
            elif phase < 2.9+visit.read_seconds:
                text(canvas,info['value'],phase-2.9,color)
                if info['state']=='stale':
                    canvas.pixel(0,0,(255,65,20));canvas.pixel(1,0,(255,65,20))
                elif info['state']=='missing':canvas.pixel(0,0,(150,150,150))
                # Quiet style-specific rail; never obscure the reading area.
                for x in range(32):
                    pattern = 3 if visit.style in ('train','counter') else 5 if visit.style in ('mine','vein') else 4
                    if (x+index)%pattern==0:canvas.pixel(x,7,shade(ORANGE,.22))
            else:
                # Reading ends in art only, including the final .6s outro.
                canvas=story(visit.style,phase,info['key'],visit.settings['bitcoin_intensity'])
    return ModulePayload(text=message,frame=[[int(c is not None) for c in row] for row in canvas.colors],color_frame=canvas.colors,scene_key=key)


def catalog():
    return {'infos':[{'key':key,'title':title,'label':label} for key,(title,label) in INFOS.items()],
            'styles':[{'key':key,'title':title,'description':description} for key,(title,description) in STYLES.items()],
            'events':[{'key':key,'title':title} for key,title in EVENTS.items()], 'defaults':deepcopy(DEFAULTS)}
