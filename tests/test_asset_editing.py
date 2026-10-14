from io import BytesIO
import unittest
from PIL import Image
from app.services.asset_editing import selection_plan, playback_timing
from app.services.assets import analyze_image, decode_image

class AssetEditingTests(unittest.TestCase):
    def test_trim_keeps_variable_durations(self):
        p=selection_plan([100,200,300,400],trim_start=1,trim_end=1)
        self.assertEqual(p['cycle_ms'],500)
        self.assertEqual(p['removed_start_ms'],100)
        self.assertEqual(p['removed_end_ms'],400)
        self.assertEqual([g['index'] for g in p['groups']],[1,2])

    def test_time_selection_rounds_out_to_full_frames(self):
        p=selection_plan([100,200,300,400],range_kind='time',start_seconds=.15,end_seconds=.59)
        self.assertEqual((p['start'],p['end']),(1,3))
        self.assertEqual((p['start_ms'],p['end_ms']),(100,600))
        self.assertEqual(selection_plan([100,200],range_kind='time',start_seconds=.1)['start'],1)

    def test_thinning_preserves_time_and_splits_long_holds(self):
        p=selection_plan([1990,33,2000,100],step=3)
        self.assertEqual(p['cycle_ms'],4123)
        self.assertEqual(sum(g['duration_ms'] for g in p['groups']),4123)
        self.assertTrue(all(33<=g['duration_ms']<=2000 for g in p['groups']))
        self.assertEqual(p['groups'][-1]['index'],3)

    def test_invalid_or_empty_ranges(self):
        for opts in ({'trim_start':3},{'trim_end':3},{'step':0},{'trim_start':-1},{'trim_start':1.5},{'range_kind':'oops'},{'range_kind':'time','start_seconds':float('nan')},{'range_kind':'time','end_seconds':.5}):
            with self.subTest(opts=opts),self.assertRaises(ValueError):selection_plan([100,100,100],**opts)

    def test_overlong_gif_can_be_analyzed_and_trimmed(self):
        frames=[Image.new('RGB',(32,8),'red' if i%2 else 'blue') for i in range(600)]
        buf=BytesIO();frames[0].save(buf,format='GIF',save_all=True,append_images=frames[1:],duration=100)
        raw=buf.getvalue();self.assertEqual(analyze_image(raw)['frame_count'],600)
        with self.assertRaises(ValueError):decode_image(raw,'Long','contain')
        data=decode_image(raw,'Trimmed','contain',trim_start=50,trim_end=50)
        self.assertEqual(len(data['frames']),500)
        data=decode_image(raw,'Thinned','contain',step=2)
        self.assertEqual(len(data['frames']),300)
        self.assertEqual(sum(f['duration_ms'] for f in data['frames']),60000)

    def test_playback_modes(self):
        self.assertEqual(playback_timing(12,6)['duration'],6)
        self.assertEqual(playback_timing(12,6,mode='once')['duration'],12)
        self.assertEqual(playback_timing(12,6,speed=2,mode='once')['duration'],6)
        self.assertEqual(playback_timing(2,6,mode='finish_loop')['duration'],6)
        self.assertEqual(playback_timing(2,5,mode='finish_loop')['duration'],6)
        self.assertEqual(playback_timing(12,6,speed=float('nan'))['speed'],1)
