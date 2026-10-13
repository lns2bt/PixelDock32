import unittest

from app.modules.btc import BTCModule
from app.services.module_visuals import ICONS


class BitcoinVisualTests(unittest.IsolatedAsyncioTestCase):
    async def test_bitcoin_has_strokes_and_separate_pulsing_orange_color(self):
        module = BTCModule()
        cache = {'btc_eur':98765, 'btc_trend':'up'}
        a = await module.render({'color_b':'#ff8000','_elapsed':0},cache)
        b = await module.render({'color_b':'#ff8000','_elapsed':.5},cache)
        self.assertEqual(a.text,'98.8k')
        self.assertEqual(a.scene_key,'bitcoin')
        for y,row in enumerate(ICONS['bitcoin']):
            for x,bit in enumerate(row):
                self.assertEqual(a.frame[y][x],int(bit))
        self.assertEqual(a.color_frame[0][1],(191,96,0))
        self.assertNotEqual(a.color_frame[0][1],b.color_frame[0][1])
        self.assertEqual(a.color_frame[1][7],(0,200,80))

    async def test_large_price_remains_readable_and_trend_arrows_differ(self):
        module = BTCModule()
        a = await module.render({}, {'btc_eur':1_234_567,'btc_trend':'up'})
        b = await module.render({}, {'btc_eur':1_234_567,'btc_trend':'down'})
        self.assertEqual(a.text,'1.2M')
        self.assertNotEqual([row[28:31] for row in a.frame[6:]], [row[28:31] for row in b.frame[6:]])
