"""Kiểm tra Mũ/Mặt nạ luôn lấy ba hàng đầu của lưới."""
import sys
import re
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Start
from catmu import HelmetSelectionDetector
from catmatna import MaskSelectionDetector


class TopNineEquipmentTests(unittest.TestCase):
    CASES = (
        ("IMG_1015.PNG", "MU", HelmetSelectionDetector),
        ("IMG_1016.PNG", "MAT_NA", MaskSelectionDetector),
        ("IMG_1017.PNG", "MAT_NA", MaskSelectionDetector),
    )

    def test_original_samples_start_at_first_row(self):
        for name, category, detector_type in self.CASES:
            path = ROOT / "input" / name
            if not path.is_file():
                self.skipTest(f"Cần ảnh mẫu {name} trong input")
            image = Start.cv2_imread_utf8(str(path))
            logs = []
            crop = detector_type().detect_and_crop(image, log_fn=logs.append)
            with self.subTest(name=name):
                self.assertEqual(Start.ImageClassifier.classify(image), category)
                self.assertEqual(crop.shape, (773, 683, 3))
                np.testing.assert_array_equal(crop, image[212:985, 1723:2406])
                self.assertIn("trên cùng", logs[-1])

    def test_resize_keeps_first_three_rows(self):
        for name, _, detector_type in self.CASES:
            path = ROOT / "input" / name
            if not path.is_file():
                self.skipTest(f"Cần ảnh mẫu {name} trong input")
            original = Start.cv2_imread_utf8(str(path))
            for scale in (0.5, 0.7372, 1.25):
                image = cv2.resize(original, None, fx=scale, fy=scale)
                logs = []
                crop = detector_type().detect_and_crop(image, log_fn=logs.append)
                match = re.search(r"outer_y=(\d+)", logs[-1])
                with self.subTest(name=name, scale=scale):
                    self.assertEqual(crop.shape, (773, 683, 3))
                    self.assertIsNotNone(match)
                    outer_y_base = int(match.group(1)) * 1284 / image.shape[0]
                    self.assertLessEqual(abs(outer_y_base - 208), 2.0)


if __name__ == "__main__":
    unittest.main()
