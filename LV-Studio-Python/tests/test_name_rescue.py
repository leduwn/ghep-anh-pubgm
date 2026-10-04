import unittest
from unittest.mock import MagicMock, patch
from PIL import Image
from ocr_engine import LevelEngine, weapon_name

class RescueTests(unittest.TestCase):
    def test_common_ocr_aliases(self):
        for text, expected in [('M4I6','M416'),('AU6','AUG'),('AUC','AUG'),('UM P45','UMP'),('AKIVI','AKM'),('M762','OTHER'),('Sau Cap','OTHER')]:
            self.assertEqual(weapon_name(text),expected)

    def test_rescue_finds_wrapped_names_without_changing_level(self):
        for name in ['M416','AUG','UMP45','AKM']:
            engine=LevelEngine('unused',device='cpu');engine.reader=MagicMock()
            engine._readtext=MagicMock(side_effect=[[([], '6/8', .99)], [([], 'unclear', .2)], [([], name, .95)]])
            with patch('ocr_engine.title_region', return_value=None):
                result=engine.recognize(Image.new('RGB',(2048,1411)))
            self.assertEqual(result['lv'],6)
            self.assertEqual(result['weapon'],'UMP' if name=='UMP45' else name)
            self.assertTrue(result['name_known'])
            self.assertEqual(engine._readtext.call_count,3)
            self.assertTrue(any(item['region']=='name-rescue' and item['accepted'] for item in result['trace']))
