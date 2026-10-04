"""Kiểm tra lọc tóc với IMG_9799.PNG; trạng thái khóa/cuộn được mô phỏng."""
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Start
from catitem import HairstyleFilter, ItemCardDetector, cv2_imread_utf8, cv2_imwrite_utf8, process_batch


class FaceAndSpecialHairTests(unittest.TestCase):
    """Không phụ thuộc IMG_9799 đang có trong input."""

    def make_screen(self, locked=()):
        templates = HairstyleFilter._load_templates()
        work = np.full((642, 1389, 3), 160, dtype=np.uint8)
        title = templates["hair_title"]
        work[60:60 + title.shape[0], 855:855 + title.shape[1]] = title
        entries = (
            ("face_side", "khuôn mặt nghiêng"),
            ("face_front", "khuôn mặt chính diện"),
            *HairstyleFilter.TARGETS,
        )
        positions = ((860, 110), (977, 110), (860, 230), (977, 230))
        for index, ((name, _), (x, y)) in enumerate(zip(entries, positions)):
            work[y:y + 108, x:x + 108] = templates[name]
            if index in locked:
                cv2.rectangle(work, (x + 86, y + 8), (x + 102, y + 29), (245, 245, 245), -1)
        return cv2.resize(work, (2778, 1284), interpolation=cv2.INTER_NEAREST)

    def test_two_face_samples_and_two_special_hairs_are_exported(self):
        image = self.make_screen()
        self.assertTrue(HairstyleFilter.is_hair_screen(image))
        self.assertEqual(len(ItemCardDetector().detect_and_crop(image, log_fn=lambda _: None)), 4)

    def test_face_samples_are_skipped_when_locked(self):
        image = self.make_screen(locked=(0, 1))
        crops = ItemCardDetector().detect_and_crop(image, log_fn=lambda _: None)
        self.assertEqual(len(crops), 2)

    def test_real_screen_finds_similar_faces_without_gray_border(self):
        path = ROOT / "input" / "IMG_1052.PNG"
        if not path.is_file():
            self.skipTest("Cần IMG_1052.PNG cho kiểm tra màn khuôn mặt thực")
        crops = ItemCardDetector().detect_and_crop(
            cv2_imread_utf8(str(path)), log_fn=lambda _: None)
        # Bốn khuôn mặt tương tự + tóc huy hiệu 4 đang mở; tóc 5 bị khóa.
        self.assertEqual(len(crops), 5)
        for face in crops[:4]:
            self.assertLess(float(np.mean(face[:, -1])), 1.0)
            self.assertLess(float(np.mean(face[-1])), 60.0)


class HairItemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / "input" / "IMG_9799.PNG"
        if not path.is_file():
            raise unittest.SkipTest("Cần ảnh mẫu IMG_9799.PNG trong input")
        cls.image = cv2_imread_utf8(str(path))

    def crops(self, image):
        return ItemCardDetector().detect_and_crop(image, log_fn=lambda _: None)

    def locked(self, indices):
        image = self.image.copy()
        # Chép dấu khóa có thật từ thẻ bên trái vào hai huy hiệu cần kiểm tra.
        # Đây là ảnh mô phỏng; không giả định đã có mẫu acc khóa cả hai tóc.
        lock = self.image[590:636, 1888:1927]
        for index in indices:
            x = (1953, 2187)[index] + 169
            image[590:636, x:x + 39] = lock
        return image

    def test_routes_to_item_and_only_exports_two_target_hairs(self):
        self.assertEqual(Start.ImageClassifier.classify(self.image), "ITEM")
        self.assertTrue(HairstyleFilter.is_hair_screen(self.image))
        crops = self.crops(self.image)
        self.assertEqual(len(crops), 4)
        self.assertTrue(all(image.shape == (216, 216, 3) for image in crops))

    def test_each_locked_hair_is_excluded(self):
        unlocked = self.crops(self.image)
        for index in (0, 1):
            with self.subTest(locked=index):
                crops = self.crops(self.locked((index,)))
                self.assertEqual(len(crops), 3)

    def test_all_locked_never_falls_back_to_generic_items(self):
        self.assertEqual(len(self.crops(self.locked((0, 1)))), 2)

    def test_other_hairs_are_not_exported_when_targets_absent(self):
        image = self.image.copy()
        image[580:802, 1950:2408] = 170
        self.assertTrue(HairstyleFilter.is_hair_screen(image))
        self.assertEqual(self.crops(image), [])

    def test_scrolling_changes_card_position(self):
        for shift in (-230, 230):
            image = self.image.copy()
            image[192:1274, 1700:2425] = 170
            image[583 + shift:799 + shift, 1953:2403] = self.image[583:799, 1953:2403]
            self.assertEqual(len(self.crops(image)), 4)

    def test_resize_jpeg_and_brightness(self):
        for scale in (0.5, 0.7372, 1.25):
            for quality in (75, 95):
                with self.subTest(scale=scale, quality=quality):
                    resized = cv2.resize(self.image, None, fx=scale, fy=scale)
                    encoded = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, quality])[1]
                    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
                    self.assertEqual(len(self.crops(image)), 4)
        for gain in (0.75, 1.15):
            adjusted = np.clip(self.image.astype(np.float32) * gain, 0, 255).astype(np.uint8)
            self.assertEqual(len(self.crops(adjusted)), 4)

    def test_other_screen_does_not_enter_hair_filter(self):
        other = ROOT / "input" / "IMG_9804.PNG"
        if not other.is_file():
            self.skipTest("Cần IMG_9804.PNG cho kiểm tra màn khác")
        self.assertFalse(HairstyleFilter.is_hair_screen(cv2_imread_utf8(str(other))))

    def test_batch_deduplicates_hairs_and_ignores_locked_screen(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input"
            output = Path(directory) / "output"
            for index, image in enumerate((self.locked((0, 1)), self.image, self.image)):
                cv2_imwrite_utf8(str(source / f"sample_{index}.png"), image)
            result = process_batch(str(source), str(output), sync_global_output=False,
                                   log_fn=lambda _: None)
            self.assertEqual(result, {"total_files": 3, "total_saved": 4})
            self.assertEqual(len(list(output.glob("item_*.png"))), 4)


if __name__ == "__main__":
    unittest.main()
