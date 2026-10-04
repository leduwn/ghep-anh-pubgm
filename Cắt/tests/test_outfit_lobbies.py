"""Kiểm tra với ảnh mẫu trong input: python -m unittest discover -s tests -v."""
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import Start
from cattrangphuc import OutfitDetector, cv2_imread_utf8, cv2_imwrite_utf8, process_batch


class OutfitLobbyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = ("IMG_9804.PNG", "IMG_9806.PNG", "IMG_9925.PNG", "IMG_9920.PNG")
        if not all((ROOT / "input" / name).is_file() for name in names):
            raise unittest.SkipTest("Cần bốn ảnh mẫu IMG_9804, 9806, 9925, 9920 trong input")
        cls.images = [cv2_imread_utf8(str(ROOT / "input" / name)) for name in names]

    def test_both_lobbies_still_route_to_outfit_tool(self):
        for image, expected in zip(self.images, ("normal", "normal", "supercar", "supercar")):
            with self.subTest(lobby=expected):
                self.assertEqual(Start.ImageClassifier.classify(image), "TRANG_PHUC")
                self.assertEqual(OutfitDetector.detect_lobby_type(image), expected)

    def test_scaled_compressed_and_brightness_variants(self):
        for image, expected in zip(self.images, ("normal", "normal", "supercar", "supercar")):
            for scale in (0.5, 0.7372, 1.25):
                with self.subTest(lobby=expected, scale=scale):
                    resized = cv2.resize(image, None, fx=scale, fy=scale)
                    encoded = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 75])[1]
                    decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
                    self.assertEqual(OutfitDetector.detect_lobby_type(decoded), expected)
            for gain in (0.75, 1.15):
                adjusted = np.clip(image.astype(np.float32) * gain, 0, 255).astype(np.uint8)
                self.assertEqual(OutfitDetector.detect_lobby_type(adjusted), expected)

    def test_supercar_crop_matches_reference_frame(self):
        detector = OutfitDetector(target_size=(642, 994))
        # Tọa độ xác định bằng so khớp ảnh số 5 với ảnh gốc IMG_9925.
        for image in self.images[2:]:
            actual = detector.detect_and_crop(image, log_fn=lambda _: None)
            np.testing.assert_array_equal(actual, image[123:1117, 786:1428])

    def test_mixed_batch_does_not_move_normal_crops(self):
        normal = OutfitDetector()
        mixed = OutfitDetector()
        normal.calibrate_batch(self.images[:2], log_fn=lambda _: None)
        mixed.calibrate_batch(self.images, log_fn=lambda _: None)
        for image in self.images[:2]:
            np.testing.assert_array_equal(
                normal.detect_and_crop(image, log_fn=lambda _: None),
                mixed.detect_and_crop(image, log_fn=lambda _: None),
            )
        # Hiệu chuẩn lại không được giữ vị trí của đợt ảnh trước.
        mixed.calibrate_batch(self.images[2:], log_fn=lambda _: None)
        self.assertIsNone(mixed._batch_anchor_x)

    def test_ceiling_alone_does_not_bypass_wardrobe_validation(self):
        image = self.images[2].copy()
        image[:, 1700:] = 0
        self.assertTrue(OutfitDetector._matches_supercar_lobby(image))
        self.assertIsNone(OutfitDetector.detect_lobby_type(image))
        self.assertIsNone(OutfitDetector.detect_lobby_type(None))
        self.assertIsNone(OutfitDetector.detect_lobby_type(np.zeros_like(image)))

    def test_batch_exports_four_images_and_reports_lobbies(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input"
            output = Path(directory) / "output"
            for index, image in enumerate(self.images):
                self.assertTrue(cv2_imwrite_utf8(str(source / f"sample_{index}.png"), image))
            logs = []
            saved = []
            result = process_batch(str(source), str(output), sync_global_output=False,
                                   log_fn=logs.append,
                                   on_card_saved_fn=lambda path, image: saved.append(path))
            self.assertEqual(result, {"total_files": 4, "total_saved": 4})
            self.assertEqual(len(saved), 4)
            for index in range(1, 5):
                image = cv2_imread_utf8(str(output / f"tp_{index:03d}.png"))
                self.assertEqual(image.shape[:2], (1220, 774))
            text = "\n".join(logs)
            self.assertIn("Sảnh thường", text)
            self.assertIn("Sảnh siêu xe", text)


if __name__ == "__main__":
    unittest.main()
