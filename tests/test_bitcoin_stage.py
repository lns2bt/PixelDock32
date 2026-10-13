import random
import time
import unittest
from collections import Counter
from app.services.bitcoin_stage import Director, FairRotation, INFOS, STYLES, EVENTS, normalize, info_value, render, presentation_timing, story, text, ORANGE
from app.services.time_stage.core import Canvas


def cache(now=1000):
    return dict(btc_eur=50000,btc_updated_at=now,btc_block_height=960000,
                btc_block_height_updated_at=now,btc_block_time=now-420,
                btc_block_details_updated_at=now,btc_block_details_height=960000,
                btc_change_24h=2.5,btc_fees={'halfHourFee':3},btc_fees_updated_at=now)


class BitcoinStageTests(unittest.TestCase):
    def test_defaults_equal_infos_and_maximum_two(self):
        d=Director();values=[]
        for _ in range(7):
            visit=d.begin({},cache(),1000)
            self.assertEqual(len(visit.infos),2)
            values.extend(info['key'] for info in visit.infos)
        self.assertEqual(Counter(values),Counter({key:2 for key in INFOS}))
        self.assertEqual(values[:8],list(INFOS)+['price'])

    def test_random_bag_is_fair_and_no_duplicates_within_visit(self):
        for count in range(1,8):
            d=Director(random.Random(count));values=[]
            for _ in range(100):
                visit=d.begin({'bitcoin_max_infos':count,'bitcoin_info_order':'random'},cache(),1000)
                keys=[v['key'] for v in visit.infos]
                self.assertEqual(len(keys),len(set(keys)));self.assertLessEqual(len(keys),count)
                values+=keys
            counts=Counter(values)
            self.assertLessEqual(max(counts.values())-min(counts.values()),1)

    def test_small_selection_returns_only_selected_once(self):
        d=Director()
        for _ in range(10):
            visit=d.begin({'bitcoin_infos':['fees'],'bitcoin_max_infos':7},cache(),1000)
            self.assertEqual([v['key'] for v in visit.infos],['fees'])

    def test_config_change_starts_new_pass_and_visits_are_frozen(self):
        d=Director();settings={'bitcoin_infos':['height','price']};data=cache()
        visit=d.begin(settings,data,1000)
        settings['bitcoin_infos'].clear();data['btc_block_height']=10
        self.assertEqual(visit.infos[0]['value'],'960000')
        self.assertEqual(d.begin({'bitcoin_infos':['fees']},data,1000).infos[0]['key'],'fees')

    def test_derived_values_and_halving_boundary(self):
        settings=normalize({});data=cache()
        self.assertEqual(info_value('price',data,settings,1000)['value'],'50.0K')
        self.assertEqual(info_value('sats',data,settings,1000)['value'],'2000')
        self.assertEqual(info_value('age',data,settings,1000)['value'],'7MIN')
        self.assertEqual(info_value('halving',data,settings,1000)['value'],'90000')
        self.assertEqual(info_value('change',data,settings,1000)['value'],'+2.5%')
        self.assertEqual(info_value('fees',data,settings,1000)['value'],'3')
        for height,expected in [(1_049_999,'1'),(1_050_000,'210000'),(6_930_000,'ENDE')]:
            data['btc_block_height']=height
            self.assertEqual(info_value('halving',data,settings,1000)['value'],expected)

    def test_staleness_missing_invalid_and_metadata_mismatch(self):
        settings=normalize({});data=cache()
        for key in INFOS:self.assertEqual(info_value(key,data,settings,1000)['state'],'fresh')
        for key in INFOS:self.assertEqual(info_value(key,data,settings,1301)['state'],'stale')
        for key in INFOS:self.assertEqual(info_value(key,{},settings,1000)['state'],'missing')
        data['btc_error']='offline';self.assertEqual(info_value('price',data,settings,1000)['state'],'stale')
        data['btc_block_details_height']=1;self.assertEqual(info_value('age',data,settings,1000)['state'],'missing')
        for bad in (float('nan'),float('inf'),-1,True,'bad'):
            data['btc_eur']=bad;self.assertEqual(info_value('price',data,settings,1000)['state'],'missing')

    def test_no_startup_event_and_single_increment_event_once(self):
        d=Director();data=cache();d.observe(data,1000)
        self.assertIsNone(d.begin({},data,1000).event)
        data['btc_block_height']+=1;d.observe(data,1001)
        visit=d.begin({},data,1001)
        self.assertEqual(visit.event,'dock');self.assertEqual(visit.old_height,960000)
        self.assertEqual(visit.new_height,960001)
        self.assertIsNone(d.begin({},data,1002).event)

    def test_sleep_reorg_jump_stale_and_disabled_do_not_celebrate(self):
        for case in ('sleep','reorg','jump','expired','disabled','error'):
            d=Director();data=cache();d.observe(data,1000)
            data['btc_block_height']+=-1 if case=='reorg' else 2 if case=='jump' else 1
            if case=='error':data['btc_block_height_error']='offline'
            d.observe(data,1001,sleeping=case=='sleep')
            visit=d.begin({'bitcoin_events':case!='disabled'},data,1122 if case=='expired' else 1002)
            self.assertIsNone(visit.event,case)

    def test_preview_does_not_consume_rotation_or_event(self):
        d=Director();data=cache();d.observe(data,1000);data['btc_block_height']+=1;d.observe(data,1001)
        for _ in range(4):self.assertIsNone(d.begin({},data,1001,preview=True).event)
        visit=d.begin({},data,1001)
        self.assertEqual(visit.event,'dock');self.assertEqual([v['key'] for v in visit.infos],['price','height'])

    def test_long_disconnect_does_not_replay_one_old_block(self):
        d=Director();data=cache();d.observe(data,1000)
        data['btc_block_height']+=1;data['btc_block_height_updated_at']=2000
        d.observe(data,2000)
        self.assertIsNone(d.begin({},data,2000).event)

    def test_long_values_extend_reading_until_full_scroll_finishes(self):
        data=cache();data['btc_block_height']=100000000
        visit=Director().begin({'bitcoin_infos':['height'],'bitcoin_read_seconds':2},data,1000)
        self.assertGreater(visit.read_seconds,5)

    def test_reading_keeps_full_configured_time_and_status_badges(self):
        for seconds in (2,4,15):
            for state in ('fresh','stale','missing'):
                with self.subTest(seconds=seconds,state=state):
                    data={} if state=='missing' else cache(0 if state=='stale' else 1000)
                    visit=Director().begin({'bitcoin_infos':['height'],'bitcoin_read_seconds':seconds},data,1000)
                    start=.8+2.9
                    first=render(visit,start+.001)
                    last=render(visit,start+seconds-.001)
                    self.assertEqual(first.color_frame,last.color_frame)
                    self.assertEqual(last.text,visit.infos[0]['label']+' '+visit.infos[0]['value'])
                    expected=(255,65,20) if state=='stale' else (150,150,150) if state=='missing' else None
                    self.assertEqual(last.color_frame[0][0],expected)

    def test_after_reading_is_art_not_previous_label_or_status_card(self):
        for style in STYLES:
            for state in ('fresh','stale','missing'):
                data={} if state=='missing' else cache(0 if state=='stale' else 1000)
                visit=Director().begin({'bitcoin_styles':[style],'bitcoin_infos':['height','fees']},data,1000)
                for index,info in enumerate(visit.infos):
                    for phase in (2.9+visit.read_seconds+.2,visit.segment-.1):
                        with self.subTest(style=style,state=state,index=index,phase=phase):
                            elapsed=.8+index*visit.segment+phase
                            result=render(visit,elapsed)
                            actual_phase=(elapsed-.8)-index*visit.segment
                            expected=story(style,actual_phase,info['key'],visit.settings['bitcoin_intensity'])
                            self.assertEqual(result.color_frame,expected.colors)
                            old_card=Canvas()
                            text(old_card,'ALT' if state=='stale' else 'FEHLT' if state=='missing' else info['label'],phase,ORANGE)
                            self.assertNotEqual(result.color_frame,old_card.colors)
                final_phase=visit.segment+.3
                self.assertEqual(render(visit,visit.duration-.3).color_frame,
                                 story(style,final_phase,'fees',visit.settings['bitcoin_intensity']).colors)
                next_label=Canvas();text(next_label,'SAT/VB',.01,ORANGE)
                self.assertEqual(render(visit,.8+visit.segment+.01).color_frame,next_label.colors)

    def test_presentation_timing_matches_ordinary_visits_and_caps_selection(self):
        for selected,maximum in ((list(INFOS),2),(['fees'],7),(['height','fees'],7)):
            settings={'bitcoin_infos':selected,'bitcoin_max_infos':maximum,'bitcoin_read_seconds':5,
                      'duration_seconds':999}
            expected={'duration':.8+min(len(selected),maximum)*9+.6,
                      'info_count':min(len(selected),maximum),'read_seconds':5.0,
                      'event_extra_seconds':6,'automatic':True}
            self.assertEqual(presentation_timing(settings),expected)
            self.assertEqual(presentation_timing(settings,cache(),1000),expected)
            visit=Director().begin(settings,cache(),1000,preview=True)
            self.assertEqual(expected['duration'],visit.duration)

    def test_presentation_timing_extends_scroll_and_does_not_consume_rotation(self):
        settings={'bitcoin_infos':['height','fees'],'bitcoin_read_seconds':2}
        data=cache();data['btc_block_height']=100000000
        director=Director()
        for _ in range(3):
            timing=presentation_timing(settings,data,1000)
        visit=director.begin(settings,data,1000)
        self.assertEqual([info['key'] for info in visit.infos],['height','fees'])
        self.assertEqual(timing['duration'],visit.duration)
        self.assertEqual(timing['read_seconds'],visit.read_seconds)
        self.assertGreater(timing['read_seconds'],2)

    def test_presentation_timing_reports_disabled_automatic(self):
        timing=presentation_timing({'bitcoin_stage':False,'bitcoin_infos':['fees'],'duration_seconds':999})
        self.assertFalse(timing['automatic'])
        self.assertEqual(timing['info_count'],1)
        self.assertEqual(timing['duration'],9.4)

    def test_every_scene_metric_deterministic_valid_distinct_and_readable(self):
        frames=[]
        for style in STYLES:
            for key in INFOS:
                visit=Director().begin({'bitcoin_styles':[style],'bitcoin_infos':[key]},cache(),1000)
                sequence=[]
                for elapsed in (.2,1,2,3.3,4.5,7.9,visit.duration,visit.duration+20):
                    result=render(visit,elapsed);self.assertEqual(result,render(visit,elapsed))
                    self.assertEqual(len(result.frame),8);self.assertEqual(len(result.frame[0]),32)
                    for row in result.color_frame:
                        for rgb in row:
                            if rgb:self.assertTrue(all(type(c) is int and 0<=c<=255 for c in rgb))
                    sequence.append(repr(result.color_frame))
                self.assertGreater(len(set(sequence)),2)
                self.assertEqual(render(visit,4.5).text,visit.infos[0]['label']+' '+visit.infos[0]['value'])
            frames.append(repr(render(visit,.2).color_frame))
        self.assertEqual(len(set(frames)),10)

    def test_event_renderers_and_duration(self):
        for key in EVENTS:
            visit=Director().begin({},cache(),1000)
            duration=visit.duration;visit.event=key;visit.old_height=960000;visit.new_height=960001
            self.assertEqual(visit.duration,duration+6)
            self.assertIn('new-block',render(visit,4).scene_key)
            self.assertNotIn('new-block',render(visit,7).scene_key)

    def test_normalization_bounds(self):
        settings=normalize({'bitcoin_max_infos':100,'bitcoin_read_seconds':'nan','bitcoin_infos':['bad'],'bitcoin_styles':{},'bitcoin_intensity':'bad'})
        self.assertEqual(settings['bitcoin_max_infos'],7);self.assertEqual(settings['bitcoin_read_seconds'],4)
        self.assertEqual(settings['bitcoin_infos'],list(INFOS));self.assertEqual(settings['bitcoin_styles'],list(STYLES))
