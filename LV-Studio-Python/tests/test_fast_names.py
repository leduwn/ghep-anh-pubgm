import unittest
from unittest.mock import MagicMock, patch
from PIL import Image
from ocr_engine import LevelEngine


def reading(text, confidence=.95):
    return [([], text, confidence)]


class FastNameTests(unittest.TestCase):
    def setUp(self):
        self.engine=LevelEngine('unused',device='cpu')
        self.engine.reader=MagicMock()
        self.image=Image.new('RGB',(2048,1411))
        self.patcher=patch('ocr_engine.title_region',return_value={'box':(10,2,1100,115),'profile':'tablet'})
        self.patcher.start();self.addCleanup(self.patcher.stop)

    def test_direct_name_skips_detector_and_never_changes_lv(self):
        self.engine._readtext=MagicMock(return_value=reading('6/8'))
        self.engine._read_line=MagicMock(return_value=reading('AKM (Cấp 8)'))
        out=self.engine.recognize(self.image)
        self.assertEqual((out['lv'],out['weapon']),(6,'AKM'))
        self.assertEqual(self.engine._readtext.call_count,1)
        self.assertGreaterEqual(out['timings']['lv_ms'],0)
        self.assertGreaterEqual(out['timings']['name_ms'],0)

    def test_low_confidence_uses_existing_detector(self):
        self.engine._readtext=MagicMock(side_effect=[reading('7/7'),reading('M416 (Cấp 7)')])
        self.engine._read_line=MagicMock(return_value=reading('AKM',.2))
        out=self.engine.recognize(self.image)
        self.assertEqual(out['weapon'],'M416')
        self.assertEqual(self.engine._readtext.call_count,2)

    def test_no_match_uses_existing_detector(self):
        self.engine._readtext=MagicMock(side_effect=[reading('7/7'),reading('UMP45')])
        self.engine._read_line=MagicMock(return_value=reading('Unreadable name'))
        out=self.engine.recognize(self.image)
        self.assertEqual(out['weapon'],'UMP')

    def test_confident_other_stops_name_work(self):
        self.engine._readtext=MagicMock(return_value=reading('4/7'))
        self.engine._read_line=MagicMock(return_value=reading('Groza (Cấp 4)'))
        out=self.engine.recognize(self.image)
        self.assertEqual((out['lv'],out['weapon']),(4,'OTHER'))
        self.assertEqual(self.engine._readtext.call_count,1)
