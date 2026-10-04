import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import numpy as np
from PIL import Image
from ocr_engine import LevelEngine
from title_regions import title_region


def reading(text, confidence=.95):
    return [([], text, confidence)]


class AdaptiveTitleTests(unittest.TestCase):
    def setUp(self):
        self.engine=LevelEngine('unused',device='cpu')
        self.engine.reader=MagicMock()
        self.image=Image.new('RGB',(2048,1411))
        self.region={'box':(10,2,1100,115),'profile':'tablet'}
        self.patcher=patch('ocr_engine.title_region',return_value=self.region)
        self.patcher.start();self.addCleanup(self.patcher.stop)

    def test_existing_research_success_never_reads_title(self):
        self.engine._readtext=MagicMock(return_value=reading('AKM 6/8'))
        self.engine._read_line=MagicMock()
        out=self.engine.recognize(self.image)
        self.assertEqual(out['lv'],6)
        self.engine._read_line.assert_not_called()

    def test_probe_progress_wins_over_title_and_keeps_three_rule(self):
        self.engine._readtext=MagicMock(side_effect=[[],reading('AKM 3/3')])
        self.engine._read_line=MagicMock()
        out=self.engine.recognize(self.image)
        self.assertEqual(out['lv'],4)
        self.engine._read_line.assert_not_called()

    def test_incomplete_progress_keeps_broad_fallback(self):
        self.engine._readtext=MagicMock(side_effect=[[],reading('Tiến độ nghiên cứu /8'),reading('AKM 6/8')])
        self.engine._read_line=MagicMock()
        out=self.engine.recognize(self.image)
        self.assertEqual(out['lv'],6)
        self.engine._read_line.assert_not_called()
        self.assertIn('top-fallback',[t['region'] for t in out['trace']])

    def test_two_matching_title_crops_skip_broad_scan(self):
        self.engine._readtext=MagicMock(side_effect=[[],[]])
        self.engine._read_line=MagicMock(side_effect=[reading('AUG (Cấp 8)'),reading('(Cấp 8)')])
        out=self.engine.recognize(self.image)
        self.assertEqual(out['lv'],8)
        self.assertEqual(out['weapon'],'AUG')
        self.assertEqual(self.engine._readtext.call_count,2)
        self.assertNotIn('top-fallback',[t['region'] for t in out['trace']])

    def test_conflicting_six_eight_does_not_accept_fast_guess(self):
        self.engine._readtext=MagicMock(side_effect=[[],[],reading('AUG (Cấp 8)')])
        self.engine._read_line=MagicMock(side_effect=[reading('AUG (Cấp 6)'),reading('(Cấp 8)')])
        out=self.engine.recognize(self.image)
        self.assertEqual(out['lv'],8)
        self.assertIn('top-fallback',[t['region'] for t in out['trace']])

    def test_uncertain_title_keeps_legacy_read(self):
        self.engine._readtext=MagicMock(side_effect=[[],[],reading('AUG (Cấp 7)')])
        self.engine._read_line=MagicMock(return_value=reading('AUG (Cấp 1)',.2))
        out=self.engine.recognize(self.image)
        self.assertEqual(out['lv'],7)


class LocateRegionTests(unittest.TestCase):
    def test_compact_top_crop_keeps_same_title_coordinates(self):
        path=Path(__file__).resolve().parents[1]/'ui'/'sample.jpg'
        with Image.open(path) as im:
            pixels=np.asarray(im.convert('RGB'))
        full=title_region(pixels)
        compact=pixels[:round(im.height*.20),:round(im.width*.80)]
        cropped=title_region(compact,(im.width,im.height))
        self.assertEqual(cropped,full)

    def test_real_phone_title_stays_in_bounds_across_resolutions(self):
        path=Path(__file__).resolve().parents[1]/'ui'/'sample.jpg'
        with Image.open(path) as im:
            for scale in (.5,1,1.5):
                resized=im.resize((round(im.width*scale),round(im.height*scale)))
                roi=title_region(np.asarray(resized.convert('RGB')))
                self.assertIsNotNone(roi)
                self.assertEqual(roi['profile'],'phone')
                x0,y0,x1,y1=roi['box']
                self.assertTrue(0<=x0<x1<=resized.width and 0<=y0<y1<=resized.height)
                self.assertGreater(x1/resized.width,.40)
                self.assertLess(y1/resized.height,.12)

    def test_blank_or_unsupported_layout_preserves_fallback(self):
        for shape in [(1411,2048,3),(946,2048,3),(2000,1000,3),(100,200,3)]:
            self.assertIsNone(title_region(np.zeros(shape,dtype=np.uint8)))
