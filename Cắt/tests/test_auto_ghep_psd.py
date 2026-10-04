import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

TOOL_FILE = Path(__file__).resolve().parents[2] / "GhepPSD" / "GhepPSD.py"
SPEC = importlib.util.spec_from_file_location("GhepPSD", TOOL_FILE)
assert SPEC is not None and SPEC.loader is not None
composer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = composer
SPEC.loader.exec_module(composer)


class AutoGhepPsdPlannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input_dir = self.root / "input"
        self.output_dir = self.root / "output"
        self.input_dir.mkdir()
        (self.output_dir / "999").mkdir(parents=True)
        self._image(self.input_dir / "profile.png", (2778, 1284), (30, 30, 30))
        self._image(self.input_dir / "lobby.png", (2778, 1284), (180, 160, 100))

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _image(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> None:
        Image.new("RGB", size, color).save(path)

    def _add(self, name: str, size: tuple[int, int]) -> None:
        self._image(self.output_dir / "999" / name, size, (80, 40, 40))

    def test_scan_and_plan_keep_every_source(self):
        for index in range(5):
            self._add(f"sung_{index + 1:03}.png", (368, 180))
        for index in range(7):
            self._add(f"tp_{index + 1:03}.png", (774, 1220))
        for index in range(3):
            self._add(f"do_{index + 1:03}.png", (683, 773))
        self._add("xe_001.png", (498, 190))
        self._add("item_001.png", (216, 216))

        categories = composer.scan_account_output("999", self.output_dir)
        form = composer.load_forms()["classic_compact"]
        plan = composer.build_layout_plan(
            "999", self.input_dir / "profile.png", self.input_dir / "lobby.png",
            categories, form, include_label_library=False,
        )

        expected = 2 + sum(len(value) for value in categories.values())
        self.assertEqual(expected, len(plan["placements"]))
        self.assertEqual(3904, plan["canvas"]["width"])
        self.assertGreater(plan["canvas"]["height"], plan["header_height"])
        self.assertEqual([], plan["groups"])
        self.assertTrue(all(item["direct_select"] for item in plan["placements"]))
        self.assertTrue(all(item["name"] == Path(item["path"]).stem for item in plan["placements"]))
        for item in plan["placements"]:
            self.assertGreater(item["width"], 0)
            self.assertGreater(item["height"], 0)
            self.assertGreaterEqual(item["x"], 0)
            self.assertGreaterEqual(item["y"], 0)
            self.assertLessEqual(item["x"] + item["width"], plan["canvas"]["width"])
            self.assertLessEqual(item["y"] + item["height"], plan["canvas"]["height"])

    def test_missing_zone_is_removed_and_width_is_reused(self):
        self._add("tp_001.png", (774, 1220))
        self._add("do_001.png", (683, 773))
        categories = composer.scan_account_output("999", self.output_dir)
        form = composer.load_forms()["classic_wide"]
        plan = composer.build_layout_plan(
            "999", self.input_dir / "profile.png", self.input_dir / "lobby.png",
            categories, form, include_label_library=False,
        )
        self.assertNotIn("left", plan["zone_bounds"])
        used_width = sum(zone["width"] for zone in plan["zone_bounds"].values())
        self.assertEqual(plan["canvas"]["width"], used_width)

    def test_header_has_three_choices_and_selected_images_fill_width(self):
        middle = self.input_dir / "middle.png"
        self._image(middle, (2778, 1284), (90, 90, 90))
        self._add("tp_001.png", (774, 1220))
        categories = composer.scan_account_output("999", self.output_dir)
        form = composer.load_forms()["classic_compact"]

        full = composer.build_layout_plan(
            "999",
            self.input_dir / "profile.png",
            self.input_dir / "lobby.png",
            categories,
            form,
            middle_profile_path=middle,
        )
        self.assertEqual(3, sum(slot["selected"] for slot in full["header_slots"]))
        headers = [item for item in full["placements"] if item["group"] == "00_HEADER"]
        self.assertEqual(3, len(headers))
        self.assertEqual([0, 1301, 2603], [item["x"] for item in headers])
        self.assertEqual(3904, sum(slot["width"] for slot in full["header_slots"]))

        missing_middle = composer.build_layout_plan(
            "999",
            self.input_dir / "profile.png",
            self.input_dir / "lobby.png",
            categories,
            form,
        )
        self.assertFalse(missing_middle["header_slots"][1]["selected"])
        headers = [item for item in missing_middle["placements"] if item["group"] == "00_HEADER"]
        self.assertEqual(2, len(headers))
        self.assertEqual([0, 1952], [item["x"] for item in headers])
        self.assertEqual([1952, 1952], [item["width"] for item in headers])
        self.assertEqual(0, missing_middle["header_slots"][1]["width"])
        self.assertEqual(1952, missing_middle["header_slots"][2]["x"])

    def test_auto_form_prefers_wide_for_large_account(self):
        categories = {name: [] for name in composer.CATEGORY_ORDER}
        sample = composer.SourceImage(Path("x.png"), "tp", 774, 1220)
        categories["tp"] = [sample] * 12
        self.assertEqual("classic_wide", composer.choose_auto_form(categories))

    def test_small_account_736_form_matches_reference_structure(self):
        categories = {name: [] for name in composer.CATEGORY_ORDER}

        def add(category: str, count: int, size: tuple[int, int]) -> None:
            for index in range(count):
                path = self.output_dir / "999" / f"{category}_{index:03}.png"
                self._image(path, size, (90, 50, 70))
                categories[category].append(composer.SourceImage(path, category, *size))

        add("sung", 11, (365, 177))
        add("xe", 3, (498, 190))
        add("luudan", 1, (216, 216))
        add("du", 1, (216, 216))
        add("item", 4, (216, 216))
        add("hd", 2, (216, 216))
        add("tp", 12, (774, 1220))
        add("do", 3, (683, 773))
        add("mu", 1, (683, 773))
        add("matna", 2, (683, 773))

        self.assertEqual("classic_small_736", composer.choose_auto_form(categories))
        reference = composer.DienLVGunSet(
            "TEST736", tuple(categories["sung"]), 2, 9, self.root / "gun_reference.png",
        )
        plan = composer.build_layout_plan(
            "999", self.input_dir / "profile.png", self.input_dir / "lobby.png",
            categories, composer.load_forms()["classic_small_736"],
            dienlv_guns=reference,
        )
        self.assertEqual(5048, plan["canvas"]["width"])
        self.assertEqual(2, plan["inventory_layout"]["columns"])
        self.assertEqual(4, plan["outfit_grid"]["columns"])
        self.assertEqual(7, plan["small_account_layout"]["rail_rows"])
        self.assertEqual(2, plan["small_account_layout"]["bottom_gun_rows"])

        left_width = plan["zone_bounds"]["left"]["width"]
        gun_x = round(left_width * composer.load_forms()["classic_small_736"]["left"]["gun_width_ratio_with_rail"])
        guns = [item for item in plan["placements"] if item["category"] == "sung"]
        cars = [item for item in plan["placements"] if item["category"] == "xe"]
        self.assertEqual([0] * 7 + [0, gun_x] * 2, [item["x"] for item in guns])
        self.assertEqual([gun_x] * 3, [item["x"] for item in cars])
        self.assertTrue(all(item["y"] >= plan["header_height"] for item in guns))
        self.assertEqual(11, len(guns))

        outfit_heights = {item["height"] for item in plan["placements"] if item["category"] == "tp"}
        inventory_heights = {item["height"] for item in plan["placements"]
                             if item["category"] in composer.INVENTORY_CATEGORIES}
        self.assertEqual(outfit_heights, inventory_heights)
        for placement in plan["placements"]:
            if placement["category"] not in {"sung", "xe", "luudan", "du", "item", "hd", "do", "mu", "matna"}:
                continue
            width, height = composer.image_size(Path(placement["path"]))
            natural = placement["width"] * height / width
            ratio = placement["height"] / natural
            self.assertGreaterEqual(ratio, 1 / 1.35 - 0.01)
            self.assertLessEqual(ratio, 1.35 + 0.01)

        for canvas_width in (3904, 5648):
            with self.subTest(canvas_width=canvas_width):
                scaled_form = copy.deepcopy(composer.load_forms()["classic_small_736"])
                scaled_form["canvas_width"] = canvas_width
                scaled = composer.build_layout_plan(
                    "999", self.input_dir / "profile.png", self.input_dir / "lobby.png",
                    categories, scaled_form, dienlv_guns=reference,
                )
                self.assertEqual(canvas_width, scaled["canvas"]["width"])
                self.assertEqual(7, scaled["small_account_layout"]["rail_rows"])
                self.assertEqual(2, scaled["small_account_layout"]["bottom_gun_rows"])
                self.assertAlmostEqual(0.266, scaled["zone_bounds"]["left"]["width"] / canvas_width, places=3)
                self.assertEqual(
                    scaled["header_height"] + max(zone["height"] for zone in scaled["zone_bounds"].values()),
                    scaled["canvas"]["height"],
                )

    def test_dienlv_reference_restores_level_layout_from_shuffled_names(self):
        dienlv_root = self.root / "DienLV" / "standalone"
        folder = dienlv_root / "TESTCODE"
        source_dir = folder / "anhle"
        source_dir.mkdir(parents=True)

        # Tên file cố tình không theo vị trí. Reference có 2 cột x 3 hàng,
        # giống cách DienLV chia danh sách theo từng cột.
        colors = {
            "IMG_005.png": (210, 20, 20),
            "IMG_001.png": (20, 210, 20),
            "IMG_004.png": (20, 20, 210),
            "IMG_002.png": (210, 210, 20),
            "IMG_003.png": (210, 20, 210),
        }
        for name, color in colors.items():
            self._image(source_dir / name, (40, 20), color)

        expected_rows = ["IMG_005.png", "IMG_002.png", "IMG_001.png", "IMG_003.png", "IMG_004.png"]
        reference = Image.new("RGB", (80, 60), (0, 0, 0))
        positions = [(0, 0), (40, 0), (0, 20), (40, 20), (0, 40)]
        for name, position in zip(expected_rows, positions):
            with Image.open(source_dir / name) as tile:
                reference.paste(tile, position)
        reference.save(folder / "TESTCODE.png")

        gun_set = composer.load_dienlv_guns("TESTCODE", dienlv_root)
        self.assertEqual(2, gun_set.columns)
        self.assertEqual(3, gun_set.rows)
        self.assertEqual(expected_rows, [item.path.name for item in gun_set.items])

    def test_inventory_input_files_stay_whole_and_are_not_grouped(self):
        self._add("do_001.png", (683, 773))
        self._add("do_002.png", (683, 773))
        self._add("mu_001.png", (683, 773))
        categories = composer.scan_account_output("999", self.output_dir)
        form = composer.load_forms()["classic_compact"]
        plan = composer.build_layout_plan(
            "999", self.input_dir / "profile.png", self.input_dir / "lobby.png",
            categories, form,
        )
        do_layers = [item for item in plan["placements"] if item["group"] == "40_INVENTORY_DO"]
        mu_layers = [item for item in plan["placements"] if item["group"] == "41_INVENTORY_MU"]
        self.assertEqual(2, len(do_layers))
        self.assertEqual(1, len(mu_layers))
        self.assertEqual("do_001.png", Path(do_layers[0]["path"]).name)
        self.assertEqual("do_002.png", Path(do_layers[1]["path"]).name)
        self.assertTrue(all(item["direct_select"] for item in do_layers + mu_layers))
        self.assertEqual(do_layers[0]["x"], do_layers[1]["x"])
        self.assertGreater(do_layers[1]["y"], do_layers[0]["y"])
        self.assertGreater(mu_layers[0]["x"], do_layers[0]["x"])
        self.assertEqual(mu_layers[0]["y"], do_layers[0]["y"])
        self.assertEqual(
            "original_input_images_as_individual_smart_objects",
            plan["inventory_layout"]["source_mode"],
        )
        self.assertEqual(3, plan["inventory_layout"]["count"])
        self.assertEqual(2, plan["inventory_layout"]["columns"])
        self.assertEqual("none", plan["inventory_layout"]["cropping"])
        self.assertNotIn("40_INVENTORY_DO", plan["groups"])
        self.assertNotIn("41_INVENTORY_MU", plan["groups"])

    def test_vehicle_height_is_stretched_to_match_gun_row(self):
        self._add("sung_001.png", (365, 176))
        self._add("sung_002.png", (365, 178))
        self._add("sung_003.png", (365, 220))
        self._add("sung_004.png", (365, 176))
        self._add("xe_001.png", (498, 190))
        self._add("du_001.png", (216, 216))
        categories = composer.scan_account_output("999", self.output_dir)
        plan = composer.build_layout_plan(
            "999", self.input_dir / "profile.png", self.input_dir / "lobby.png",
            categories, composer.load_forms()["classic_compact"],
        )
        guns = [item for item in plan["placements"] if item["group"] == "10_GUNS"]
        gun = guns[0]
        vehicle = next(item for item in plan["placements"] if item["group"] == "20_VEHICLES")
        extra = next(item for item in plan["placements"] if item["group"] == "50_EXTRAS")
        self.assertEqual(1, len({item["height"] for item in guns}))
        self.assertEqual(gun["height"], vehicle["height"])
        self.assertEqual(gun["height"], extra["height"])
        self.assertEqual(gun["y"], vehicle["y"])

    def test_portable_path_config_is_loaded(self):
        self.assertTrue(composer.CONFIG_PATH.is_file())
        self.assertEqual("config.json", composer.CONFIG_PATH.name)
        self.assertEqual((composer.PROJECT_ROOT.parent / "Cắt" / "input").resolve(), composer.INPUT_DIR)
        self.assertEqual((composer.PROJECT_ROOT.parent / "Cắt" / "output").resolve(), composer.OUTPUT_DIR)
        self.assertEqual((composer.PROJECT_ROOT.parent / "DienLV" / "standalone").resolve(), composer.DIENLV_ROOT)

    def test_results_go_directly_in_account_folder_without_overwriting(self):
        results = self.root / "results"
        account_folder = composer.create_run_folder("999", results)
        self.assertEqual(results / "999", account_folder)
        first = composer.choose_run_files("999", account_folder)
        self.assertEqual(account_folder / "999.psd", first.psd)
        self.assertEqual(account_folder / "xem_truoc.jpg", first.preview)
        first.psd.touch()
        second = composer.choose_run_files("999", account_folder)
        self.assertEqual(account_folder / "999_02.psd", second.psd)
        self.assertEqual(account_folder / "999_02.png", second.png)
        self.assertEqual(account_folder / "layout_02.json", second.layout)
        self.assertEqual(account_folder / "xem_truoc_02.jpg", second.preview)

    def test_new_dienlv_code_appears_without_restarting(self):
        root = self.root / "guns"
        root.mkdir()
        self.assertEqual([], composer.list_dienlv_codes(root))
        folder = root / "NEWCODE"
        (folder / "anhle").mkdir(parents=True)
        self._image(folder / "anhle" / "gun.png", (40, 20), (80, 50, 50))
        self._image(folder / "NEWCODE.png", (40, 20), (80, 50, 50))
        self.assertEqual("NEWCODE", composer.list_dienlv_codes(root)[0]["code"])

    def test_red_background_vehicles_are_sorted_first(self):
        self._image(self.output_dir / "999" / "xe_001.png", (498, 190), (105, 48, 88))
        self._image(self.output_dir / "999" / "xe_002.png", (498, 190), (130, 52, 52))
        self._image(self.output_dir / "999" / "xe_003.png", (498, 190), (72, 58, 102))
        self._image(self.output_dir / "999" / "xe_004.png", (498, 190), (128, 50, 50))
        categories = composer.scan_account_output("999", self.output_dir)
        self.assertEqual(
            ["xe_002.png", "xe_004.png", "xe_001.png", "xe_003.png"],
            [item.path.name for item in categories["xe"]],
        )

    def test_outfit_grid_follows_supported_exact_counts(self):
        for count, expected in {12: (3, 4), 15: (3, 5), 20: (4, 5), 36: (6, 6)}.items():
            with self.subTest(count=count):
                categories = {name: [] for name in composer.CATEGORY_ORDER}
                categories["tp"] = [
                    composer.SourceImage(Path(f"tp_{index}.png"), "tp", 774, 1220)
                    for index in range(count)
                ]
                plan = composer.build_layout_plan(
                    "999", self.input_dir / "profile.png", self.input_dir / "lobby.png",
                    categories, composer.load_forms()["classic_wide"],
                )
                self.assertEqual(expected[0], plan["outfit_grid"]["rows"])
                self.assertEqual(expected[1], plan["outfit_grid"]["columns"])
                outfits = [item for item in plan["placements"] if item["group"] == "30_OUTFITS"]
                self.assertEqual(expected[0], len({item["y"] for item in outfits}))
                self.assertEqual(expected[1], len({item["x"] for item in outfits}))
                self.assertTrue(all(item["direct_select"] for item in outfits))
                self.assertNotIn("30_OUTFITS", plan["groups"])


    def test_vehicles_sorted_by_tickets_3ve_1ve_vip_none(self):
        v1 = composer.SourceImage(Path("xe_001.png"), "xe", 498, 190)
        v2 = composer.SourceImage(Path("xe_002.png"), "xe", 498, 190)
        v3 = composer.SourceImage(Path("xe_003.png"), "xe", 498, 190)
        v4 = composer.SourceImage(Path("xe_004.png"), "xe", 498, 190)
        choices = {
            "xe_001.png": "none",
            "xe_002.png": "vip",
            "xe_003.png": "ticket_1_2c",
            "xe_004.png": "ticket_3_4c",
        }
        ordered = composer.sorted_vehicles([v1, v2, v3, v4], choices)
        # Expected priority: 3 vé (xe_004) -> 1 vé (xe_003) -> VIP (xe_002) -> None (xe_001)
        self.assertEqual(
            ["xe_004.png", "xe_003.png", "xe_002.png", "xe_001.png"],
            [item.path.name for item in ordered],
        )

    def test_labels_and_layers_are_flat_without_groups(self):
        self._add("sung_001.png", (368, 180))
        self._add("xe_001.png", (498, 190))
        self._add("tp_001.png", (774, 1220))
        categories = composer.scan_account_output("999", self.output_dir)
        plan = composer.build_layout_plan(
            "999", self.input_dir / "profile.png", self.input_dir / "lobby.png",
            categories, composer.load_forms()["classic_compact"],
            include_label_library=False,
            outfit_choices={"tp_001.png": "vip"},
            vehicle_choices={"xe_001.png": "ticket_1_2c"},
        )
        self.assertEqual([], plan["groups"])
        self.assertNotIn("21_VEHICLE_LABELS", plan["groups"])
        self.assertNotIn("31_OUTFIT_LABELS", plan["groups"])
        self.assertTrue(all(item["direct_select"] for item in plan["placements"]))
        label_layers = [item for item in plan["placements"] if item["category"] in {"vehicle_label", "outfit_label"}]
        self.assertEqual(2, len(label_layers))
        for layer in label_layers:
            self.assertIsNone(layer["group"])
            self.assertTrue(layer["direct_select"])

    def test_dienlv_counter_detection_and_composite(self):
        import sys
        dienlv_dir = Path(__file__).resolve().parents[2] / "DienLV"
        if str(dienlv_dir) not in sys.path:
            sys.path.insert(0, str(dienlv_dir))
        import dienlv
        import numpy as np

        # 1. Plain image (no counter) -> None
        plain_img = np.full((1284, 2778, 3), (60, 48, 35), dtype=np.uint8)
        self.assertIsNone(dienlv.detect_and_crop_counter(plain_img))

        # 2. Grey counter (monochrome, like Image 4) -> None
        grey_img = plain_img.copy()
        # Draw a grey box with digits in the counter ROI (y: 120-190, x: 1810-2120)
        grey_img[120:190, 1810:2120] = 80
        # Draw some edges / grey text
        grey_img[130:180, 1850:2100:10] = 200
        self.assertIsNone(dienlv.detect_and_crop_counter(grey_img))

        # 3. Colorful counter (like Image 1 & 2) -> returns cropped badge
        color_img = plain_img.copy()
        # Blue frame (B=200, G=100, R=20)
        color_img[125:190, 1815:2118] = (200, 100, 20)
        # Bright digit stripes inside
        color_img[135:180, 1920:2100:15] = (255, 255, 255)
        # Red crest on left (B=20, G=40, R=220)
        color_img[125:185, 1815:1870] = (20, 40, 220)

        badge = dienlv.detect_and_crop_counter(color_img)
        self.assertIsNotNone(badge)
        self.assertGreater(badge.shape[1], 100)
        self.assertGreater(badge.shape[0], 20)

        # 4. Elongated counter effect (like AKM Glacier ice smoke) -> trimmed to standard aspect ratio
        elongated_img = plain_img.copy()
        # Main counter body
        elongated_img[125:190, 1815:2118] = (200, 100, 20)
        elongated_img[135:180, 1920:2100:15] = (255, 255, 255)
        elongated_img[125:185, 1815:1870] = (20, 40, 220)
        # Extra smoke effect extending down from left crest (y: 190 to 280)
        elongated_img[190:280, 1815:1850] = (20, 40, 220)
        elongated_badge = dienlv.detect_and_crop_counter(elongated_img)
        self.assertIsNotNone(elongated_badge)
        # Ratio should adhere to standard majority (>= 3.8) instead of stretching down
        ratio = elongated_badge.shape[1] / elongated_badge.shape[0]
        self.assertGreaterEqual(ratio, 3.8)

        # 5. Composite badge onto card (like Image 3)
        card = np.full((178, 365, 3), (50, 50, 180), dtype=np.uint8)
        composited = dienlv.apply_counter_badge(card, badge)
        self.assertEqual(card.shape, composited.shape)
        # Bottom-right corner should now have badge colors, not original card color
        self.assertFalse(np.array_equal(composited[-10:, -10:], card[-10:, -10:]))

    def test_catsung_tool_and_gheppsd_auto_select(self):
        import sys
        import shutil
        catsung_dir = Path(__file__).resolve().parents[1] / "tool" / "Cắt Súng"
        if str(catsung_dir) not in sys.path:
            sys.path.insert(0, str(catsung_dir))
        import catsung

        self.assertTrue(callable(getattr(catsung, "process_batch", None)))
        self.assertTrue(callable(getattr(catsung, "detect_and_crop_counter", None)))
        self.assertTrue(callable(getattr(catsung, "apply_counter_badge", None)))

        # Test GhepPSD finds gun set in Cắt/output/<acc>
        test_acc = "AUTOGUN_TEST"
        test_out = composer.OUTPUT_DIR / test_acc
        (test_out / "anhle").mkdir(parents=True, exist_ok=True)
        self._image(test_out / "anhle" / "sung_001.png", (40, 20), (50, 50, 200))
        self._image(test_out / f"{test_acc}.png", (80, 20), (50, 50, 200))

        try:
            folder, images, ref = composer._dienlv_source_paths(test_acc)
            self.assertEqual(folder, test_out)
            self.assertEqual(len(images), 1)
            self.assertEqual(ref, test_out / f"{test_acc}.png")

            # Check it shows up in list_dienlv_codes
            codes = [item["code"] for item in composer.list_dienlv_codes()]
            self.assertIn(test_acc, codes)
        finally:
            shutil.rmtree(test_out, ignore_errors=True)
    def test_gun_priority_and_grouping_sort(self):
        import sys
        catsung_dir = Path(__file__).resolve().parents[1] / "tool" / "Cắt Súng"
        if str(catsung_dir) not in sys.path:
            sys.path.insert(0, str(catsung_dir))
        import catsung
        import numpy as np

        dummy = np.zeros((10, 10, 3), dtype=np.uint8)
        counter = np.zeros((5, 5, 3), dtype=np.uint8)

        def make_item(name, level, ocr, has_counter, idx):
            return catsung.ProcessedImage(
                index=idx,
                file_name=name,
                crop=dummy,
                gun_crop=dummy,
                level=level,
                ocr_text=ocr,
                counter_crop=counter if has_counter else None,
            )

        items = [
            make_item("AKM_LV6", 6, "AKM Băng", False, 1),
            make_item("UMP_LV4", 4, "UMP45 Hoả Long", False, 2),
            make_item("M416_LV7_NO_COUNTER", 7, "M416 Nguyệt Thực", False, 3),
            make_item("AWM_LV7_COUNTER", 7, "AWM Lôi Thần", True, 4),
            make_item("AUG_LV8_COUNTER", 8, "AUG Phúc Lộc", True, 5),
            make_item("M416_LV8_NO_COUNTER", 8, "M416 Kim Hầu", False, 6),
            make_item("AKM_LV7_COUNTER", 7, "AKM Sa Mạc", True, 7),
            make_item("M416_LV7_SKIN2_COUNTER", 7, "M416 Thần Tài", True, 8),
            make_item("AUG_LV7_NO_COUNTER", 7, "AUG Băng", False, 9),
            make_item("M416_LV8_COUNTER", 8, "M416 Băng Giá", True, 10),
            make_item("UMP_LV7_COUNTER", 7, "UMP Huyết Nguyệt", True, 11),
            make_item("M416_LV7_SKIN1_COUNTER", 7, "M416 Khủng Long", True, 12),
            make_item("AUG_LV7_COUNTER", 7, "AUG Thiên Thần", True, 13),
        ]

        sorted_items = catsung.sort_processed_images(items)
        sorted_names = [it.file_name for it in sorted_items]

        expected_names = [
            "M416_LV8_COUNTER",
            "AUG_LV8_COUNTER",
            "M416_LV8_NO_COUNTER",
            "M416_LV7_SKIN2_COUNTER",
            "M416_LV7_SKIN1_COUNTER",
            "AUG_LV7_COUNTER",
            "UMP_LV7_COUNTER",
            "AKM_LV7_COUNTER",
            "AWM_LV7_COUNTER",
            "M416_LV7_NO_COUNTER",
            "AUG_LV7_NO_COUNTER",
            "AKM_LV6",
            "UMP_LV4",
        ]
        self.assertEqual(expected_names, sorted_names)




if __name__ == "__main__":
    unittest.main()
