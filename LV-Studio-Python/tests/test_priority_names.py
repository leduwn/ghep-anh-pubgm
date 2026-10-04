import unittest
from unittest.mock import MagicMock
from PIL import Image
from ocr_engine import LevelEngine, weapon_name

class PriorityTests(unittest.TestCase):
    def engine(self, responses):
        engine=LevelEngine('unused',device='cpu')
        engine.reader=MagicMock()
        engine.reader.readtext.side_effect=responses
        return engine

    def test_only_four_output_names(self):
        for text,name in [('M416','M416'),('AUG','AUG'),('UMP45','UMP'),('AKM','AKM'),('M762','OTHER'),('SCAR-L','OTHER'),('GROZA','OTHER')]:
            self.assertEqual(weapon_name(text),name)

    def test_unknown_name_gets_rescue_pass_after_fast_pass(self):
        engine=self.engine([[([], '7/7', .99)],[([], 'Unclear', .3)],[([], 'Unclear', .3)]])
        result=engine.recognize(Image.new('RGB',(1536,706)))
        self.assertEqual((result['lv'],result['weapon']),(7,'OTHER'))
        self.assertEqual(engine.reader.readtext.call_count,3)

    def test_known_other_in_lv_text_skips_name_ocr(self):
        engine=self.engine([[([], 'M762 6/7', .99)]])
        result=engine.recognize(Image.new('RGB',(1536,706)))
        self.assertEqual((result['lv'],result['weapon']),(6,'OTHER'))
        self.assertEqual(engine.reader.readtext.call_count,1)

    def test_priority_in_lv_text_skips_name_ocr(self):
        engine=self.engine([[([], 'AKM 8/8', .99)]])
        result=engine.recognize(Image.new('RGB',(1536,706)))
        self.assertEqual((result['lv'],result['weapon']),(8,'AKM'))
        self.assertEqual(engine.reader.readtext.call_count,1)
