"""Unit tests for OCR level, weapon name, elimination counter, and UID parsers."""

import pytest

from ocr.models import OCRObservation, UIDCandidate
from ocr.parsers import (
    normalize_unicode_text,
    parse_gun_level,
    parse_gun_name,
    parse_kill_counter,
    parse_progress_level,
    parse_roman_level,
    parse_title_level,
    parse_uid,
)
from ocr.uid_ocr import resolve_uid_consensus


class TestLevelParsers:
    def test_progress_level_standard(self):
        res = parse_progress_level("Tiến độ: 1/7")
        assert res is not None
        assert res["lv"] == 1
        assert res["current"] == 1
        assert res["maximum"] == 7
        assert res["source"] == "progress"

        res = parse_progress_level("Cấp: 4/7")
        assert res is not None
        assert res["lv"] == 4

        res = parse_progress_level("7/7")
        assert res is not None
        assert res["lv"] == 7

    def test_progress_level_legacy_three_of_three(self):
        # PUBG upgrade workshop quirk: 3/3 represents level 4 on 3-step skins
        res = parse_progress_level("3/3")
        assert res is not None
        assert res["lv"] == 4
        assert res["current"] == 3
        assert res["maximum"] == 3

    def test_progress_level_roman_and_characters(self):
        res = parse_progress_level("I/7")
        assert res is not None
        assert res["lv"] == 1

        res = parse_progress_level("l / 5")
        assert res is not None
        assert res["lv"] == 1

    def test_progress_level_unicode_fractions(self):
        # Slash fraction symbol normalization
        res = parse_progress_level("4⁄7")
        assert res is not None
        assert res["lv"] == 4

    def test_progress_level_invalid(self):
        assert parse_progress_level("25/7") is None
        assert parse_progress_level("abc") is None
        assert parse_progress_level("0/0") is None

    def test_roman_level(self):
        assert parse_roman_level("I") == 1
        assert parse_roman_level("IV") == 4
        assert parse_roman_level("VII") == 7
        assert parse_roman_level("X") == 10
        assert parse_roman_level("XX") == 20
        assert parse_roman_level("IIII") is None

    def test_title_level_numeric(self):
        res = parse_title_level("Cấp 4")
        assert res is not None
        assert res["lv"] == 4

        res = parse_title_level("LV. 7")
        assert res is not None
        assert res["lv"] == 7

        res = parse_title_level("Level: 1")
        assert res is not None
        assert res["lv"] == 1

    def test_title_level_confused_characters(self):
        res = parse_title_level("Cấp G")
        assert res is not None
        assert res["lv"] == 6

        res = parse_title_level("Cấp I")
        assert res is not None
        assert res["lv"] == 1

    def test_title_level_roman(self):
        res = parse_title_level("M416 (IV)")
        assert res is not None
        assert res["lv"] == 4

    def test_parse_gun_level_cascade(self):
        # Progress preferred over title
        obs = [
            OCRObservation(text="M416 Cấp 5", confidence=0.88),
            OCRObservation(text="4/7", confidence=0.95),
        ]
        lv, src, conf, reasons, raw = parse_gun_level(obs)
        assert lv == 4
        assert src == "progress"
        assert conf == 0.95

        # Title fallback when progress absent
        obs_title = [OCRObservation(text="M416 Cấp 6", confidence=0.90)]
        lv_t, src_t, conf_t, reasons_t, raw_t = parse_gun_level(obs_title)
        assert lv_t == 6
        assert src_t == "title"
        assert any("fallback" in r.lower() for r in reasons_t)


class TestWeaponNameParser:
    def test_canonical_weapons(self):
        for name in ["M416", "AUG", "AKM", "AWM", "M24", "KAR98K", "GROZA", "VECTOR", "UMP"]:
            obs = [OCRObservation(text=f"{name} Băng Giá", confidence=0.98)]
            parsed_name, conf, reasons, _ = parse_gun_name(obs)
            assert parsed_name == name
            assert conf == 0.98
            assert len(reasons) == 0

    def test_safe_aliases(self):
        # AU6 -> AUG
        obs = [OCRObservation(text="AU6 Hoàng Kim", confidence=0.90)]
        name, conf, reasons, _ = parse_gun_name(obs)
        assert name == "AUG"
        assert any("alias" in r.lower() for r in reasons)

        # AKIVI -> AKM
        obs = [OCRObservation(text="AKIVI Hoả Ngục", confidence=0.92)]
        name, conf, reasons, _ = parse_gun_name(obs)
        assert name == "AKM"

    def test_unknown_weapon_no_hallucination(self):
        obs = [OCRObservation(text="Sung Luc Phun Nuoc", confidence=0.95)]
        name, conf, reasons, _ = parse_gun_name(obs)
        assert name is None
        assert conf == 0.0
        assert any("unknown" in r.lower() for r in reasons)


class TestKillCounterParser:
    def test_counter_with_presence(self):
        obs = [OCRObservation(text="1284", confidence=0.96)]
        counter, conf, reasons, _ = parse_kill_counter(obs, counter_present=True)
        assert counter == "1284"
        assert conf == 0.96

    def test_counter_without_presence(self):
        obs = [OCRObservation(text="1284", confidence=0.96)]
        counter, conf, reasons, _ = parse_kill_counter(obs, counter_present=False)
        assert counter is None
        assert any("not visually present" in r.lower() for r in reasons)

    def test_counter_no_digits(self):
        obs = [OCRObservation(text="NONE", confidence=0.90)]
        counter, conf, reasons, _ = parse_kill_counter(obs, counter_present=True)
        assert counter is None
        assert any("no numeric" in r.lower() for r in reasons)


class TestUIDParserAndConsensus:
    def test_single_box_uid(self):
        obs = [OCRObservation(text="UID: 5123456789", confidence=0.95)]
        cands = parse_uid(obs, source_id="s1")
        assert len(cands) == 1
        assert cands[0].uid == "5123456789"
        assert cands[0].has_label is True

    def test_single_box_digit_normalization(self):
        # Letters O -> 0, l -> 1
        obs = [OCRObservation(text="UID: 5l2345678O", confidence=0.92)]
        cands = parse_uid(obs, source_id="s1")
        assert len(cands) == 1
        assert cands[0].uid == "5123456780"

    def test_split_box_adjacent(self):
        obs = [
            OCRObservation(
                text="UID:",
                box=[[100, 500], [140, 500], [140, 520], [100, 520]],
                confidence=0.90,
            ),
            OCRObservation(
                text="5123456789",
                box=[[148, 501], [250, 501], [250, 521], [148, 521]],
                confidence=0.96,
            ),
        ]
        cands = parse_uid(obs, source_id="s1")
        assert len(cands) == 1
        assert cands[0].uid == "5123456789"
        assert cands[0].roi_name == "primary_split"

    def test_split_box_rejected_when_distant(self):
        obs = [
            OCRObservation(
                text="UID:",
                box=[[100, 500], [140, 500], [140, 520], [100, 520]],
                confidence=0.90,
            ),
            # Distant horizontal box (x=800)
            OCRObservation(
                text="5123456789",
                box=[[800, 500], [900, 500], [900, 520], [800, 520]],
                confidence=0.96,
            ),
        ]
        cands = parse_uid(obs, source_id="s1")
        assert len(cands) == 0

    def test_multi_source_consensus_boost(self):
        cands = [
            UIDCandidate(uid="5123456789", confidence=0.90, source_id="s1", raw_text="UID: 5123456789"),
            UIDCandidate(uid="5123456789", confidence=0.92, source_id="s2", raw_text="UID: 5123456789"),
            UIDCandidate(uid="5123456789", confidence=0.91, source_id="s3", raw_text="UID: 5123456789"),
        ]
        res = resolve_uid_consensus(cands)
        assert res.uid == "5123456789"
        assert res.sources_count == 3
        # Boosted beyond individual confidences
        assert res.confidence > 0.92
        assert not res.has_conflict
        assert not res.review_required

    def test_multi_source_conflict_detection(self):
        cands = [
            UIDCandidate(uid="5123456789", confidence=0.95, source_id="s1", raw_text="UID: 5123456789"),
            UIDCandidate(uid="5999999999", confidence=0.94, source_id="s2", raw_text="UID: 5999999999"),
        ]
        res = resolve_uid_consensus(cands)
        assert res.has_conflict is True
        assert res.review_required is True
        assert any("conflict" in r.lower() for r in res.reasons)
