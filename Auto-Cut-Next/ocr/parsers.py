"""Domain-specific OCR parsers for PUBG Mobile levels, weapon names, kill counters, and UIDs."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional, Tuple

from .models import OCRObservation, UIDCandidate

CANONICAL_WEAPONS: list[tuple[str, str]] = [
    ("M416", r"\bM[4A][1IL|][6GE]\b|M416"),
    ("AUG", r"\bAUG\b"),
    ("UMP", r"\bUMP(?:45|9)?\b"),
    ("AKM", r"\bAKM\b"),
    ("SCAR-L", r"\bSCAR-?L\b"),
    ("M762", r"\b(?:BERYL\s*)?M762\b"),
    ("M16A4", r"\bM16A4\b"),
    ("ACE32", r"\bACE32\b"),
    ("G36C", r"\bG36C\b"),
    ("QBZ", r"\bQBZ\b"),
    ("FAMAS", r"\bFAMAS\b"),
    ("GROZA", r"\bGROZA\b"),
    ("P90", r"\bP90\b"),
    ("VECTOR", r"\bVECTOR\b"),
    ("UZI", r"\bUZI\b"),
    ("PP19", r"\b(?:PP-?19|BIZON)\b"),
    ("MP5K", r"\bMP5K\b"),
    ("TOMMY GUN", r"\b(?:TOMMY|THOMPSON)\b"),
    ("M249", r"\bM249\b"),
    ("DP28", r"\bDP-?28\b"),
    ("MG3", r"\bMG3\b"),
    ("AWM", r"\bAWM\b"),
    ("AMR", r"\bAMR\b"),
    ("M24", r"\bM24\b"),
    ("KAR98K", r"\bKAR98K\b"),
    ("MINI14", r"\bMINI14\b"),
    ("SKS", r"\bSKS\b"),
    ("SLR", r"\bSLR\b"),
    ("MK14", r"\bMK14\b"),
    ("MK12", r"\bMK12\b"),
    ("VSS", r"\bVSS\b"),
    ("QBU", r"\bQBU\b"),
    ("DBS", r"\bDBS\b"),
    ("S12K", r"\bS12K\b"),
    ("S686", r"\bS686\b"),
    ("S1897", r"\bS1897\b"),
    ("NS2000", r"\bNS2000\b"),
    ("M1014", r"\bM1014\b"),
    ("HONEY BADGER", r"\bHONEY\s*BADGER\b"),
]

PRIORITY_WEAPONS: set[str] = {"M416", "AUG", "UMP", "AKM"}


def normalize_unicode_text(text: str) -> str:
    """Normalizes Unicode text, removes diacritics, and unifies slash characters."""
    normalized = unicodedata.normalize("NFKC", str(text)).replace("⁄", "/").replace("∕", "/")
    return "".join(c for c in unicodedata.normalize("NFD", normalized) if not unicodedata.combining(c))


def parse_progress_level(text: str) -> Optional[dict[str, Any]]:
    """Extracts upgrade progress ratio x/y, handling the legacy 3/3 -> 4 level conversion."""
    norm = normalize_unicode_text(text)
    match = re.search(r"(?<![\dA-Za-z])(\d{1,2}|[Il|V])\s*/\s*(\d{1,2})(?!\d)", norm)
    if not match:
        return None

    raw_curr = match.group(1)
    current = 1 if raw_curr in {"I", "l", "|", "V"} else int(raw_curr)
    maximum = int(match.group(2))

    if not (1 <= current <= maximum <= 20):
        return None

    # PUBG upgrade workshop legacy rule: 3/3 represents level 4 on three-step gun skins
    effective_lv = 4 if (current, maximum) == (3, 3) else current
    return {
        "lv": effective_lv,
        "current": current,
        "maximum": maximum,
        "source": "progress",
        "raw": match.group(0),
    }


def parse_roman_level(token: str) -> Optional[int]:
    """Parses a Roman numeral token in range I..XX."""
    cleaned = token.upper().replace("|", "I").replace("L", "I")
    values = {"I": 1, "V": 5, "X": 10}
    if not cleaned or any(c not in values for c in cleaned):
        return None

    val = sum(
        -values[c] if i + 1 < len(cleaned) and values[c] < values[cleaned[i + 1]] else values[c]
        for i, c in enumerate(cleaned)
    )
    valid_roman = [
        "", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
        "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
    ]
    return val if (1 <= val <= 20 and val < len(valid_roman) and valid_roman[val] == cleaned) else None


def parse_title_level(text: str) -> Optional[dict[str, Any]]:
    """Extracts level from section title strings (e.g. 'Cấp 4', 'Lv.7', 'Level IV')."""
    norm = normalize_unicode_text(text).strip()

    # Numeric level: "Cap 4", "LV.7", "Level 1"
    match = re.search(r"\b(?:Cap|Cấp|LV|Level)\s*[:.\-]?\s*(\d{1,2})(?!\d)", norm, re.IGNORECASE)
    if match:
        val = int(match.group(1))
        if 1 <= val <= 20:
            return {"lv": val, "source": "title", "raw": match.group(0)}

    # OCR character confusion: G -> 6, Il| -> 1
    match = re.search(r"\b(?:Cap|Cấp|LV|Level)\s*([GIl|])\s*[).,;]*\s*$", norm, re.IGNORECASE)
    if match:
        char = match.group(1).upper()
        val = 6 if char == "G" else 1
        return {"lv": val, "source": "title", "raw": match.group(0)}

    # Roman numeral suffix: "M416 (IV)", "Level VII"
    match = re.search(r"(?:^|[\s(\[\-:])([IVXil|]{1,8})\s*[)\].,;]*\s*$", norm, re.IGNORECASE)
    if match:
        roman_val = parse_roman_level(match.group(1))
        if roman_val is not None:
            return {"lv": roman_val, "source": "title", "raw": match.group(0)}

    return None


def parse_gun_level(
    observations: list[OCRObservation],
) -> Tuple[Optional[int], str, float, list[str], Optional[str]]:
    """Evaluates observations to determine gun upgrade level.

    Returns:
        tuple[level, level_source, confidence, review_reasons, raw_text]
    """
    if not observations:
        return None, "none", 0.0, ["No text recognized in level ROI"], None

    texts = [o.text for o in observations]
    confs = [o.confidence for o in observations]
    combined_text = " ".join(texts)
    avg_conf = float(sum(confs) / len(confs)) if confs else 0.0

    # Primary pass: check each observation and combined string for progress ratio
    for i, t in enumerate(texts + [combined_text]):
        prog = parse_progress_level(t)
        if prog:
            conf = confs[i] if i < len(confs) else avg_conf
            return prog["lv"], "progress", conf, [], prog["raw"]

    # Secondary pass: fallback to title level
    for i, t in enumerate(texts + [combined_text]):
        title = parse_title_level(t)
        if title:
            conf = confs[i] if i < len(confs) else avg_conf
            # Title fallback carries slightly lower base confidence and warning
            return (
                title["lv"],
                "title",
                conf * 0.9,
                ["Level parsed from title fallback instead of progress bar"],
                title["raw"],
            )

    return None, "none", 0.0, ["No valid level pattern recognized in ROI"], combined_text


def parse_gun_name(
    observations: list[OCRObservation],
) -> Tuple[Optional[str], float, list[str], Optional[str]]:
    """Matches text against the canonical 38-weapon dictionary with safe aliases.

    Returns:
        tuple[weapon_name, confidence, review_reasons, raw_text]
    """
    if not observations:
        return None, 0.0, ["No text recognized in name ROI"], None

    texts = [o.text for o in observations]
    combined = " ".join(texts)
    norm = normalize_unicode_text(combined).upper()
    compact = re.sub(r"\s+", "", norm)

    # 1. Direct regex match on canonical weapons
    for name, pattern in CANONICAL_WEAPONS:
        if re.search(pattern, norm, re.IGNORECASE) or re.search(pattern, compact, re.IGNORECASE):
            conf = max(o.confidence for o in observations)
            return name, conf, [], combined

    # 2. Common OCR character confusion aliases for high-priority weapons
    for name, alias in [("AUG", r"\bAU[6C]\b"), ("AKM", r"\bAKIVI\b"), ("UMP", r"\bU[1Il|]vlP\b")]:
        if re.search(alias, norm, re.IGNORECASE):
            conf = max(o.confidence for o in observations)
            return name, conf * 0.92, [f"Weapon name matched via safe alias: {name}"], combined

    return None, 0.0, ["Unknown weapon name; manual review required"], combined


def parse_kill_counter(
    observations: list[OCRObservation],
    counter_present: bool,
) -> Tuple[Optional[str], float, list[str], Optional[str]]:
    """Extracts numeric kill counter digits. Requires prior visual presence confirmation.

    Returns:
        tuple[kill_counter, confidence, review_reasons, raw_text]
    """
    if not counter_present:
        return None, 0.0, ["Elimination tracker badge not visually present"], None

    if not observations:
        return None, 0.0, ["No text recognized in elimination counter ROI"], None

    texts = [o.text for o in observations]
    combined = " ".join(texts)

    # Clean digits
    digits_found = re.findall(r"\d+", combined)
    if not digits_found:
        return None, 0.0, ["No numeric digits found in elimination counter ROI"], combined

    counter_str = "".join(digits_found)
    if not (1 <= len(counter_str) <= 8):
        return None, 0.0, [f"Counter digits length out of bounds ({len(counter_str)})"], combined

    conf = max(o.confidence for o in observations)
    return counter_str, conf, [], combined


def parse_uid(
    observations: list[OCRObservation],
    source_id: str,
    roi_name: str = "primary",
) -> list[UIDCandidate]:
    """Extracts PUBG Mobile UID candidates supporting single-box and adjacent split-box formats."""
    if not observations:
        return []

    candidates: list[UIDCandidate] = []

    # 1. Single-box labeled extraction (e.g. 'UID: 5123456789' or 'ID: 5123456789')
    for obs in observations:
        text = obs.text
        match = re.search(r"\bU?[I1l|]D\s*[:：\-]?\s*([0-9OoIl|\s]{8,22})\b", text, re.IGNORECASE)
        if match:
            raw_digits = match.group(1)
            # Safe character normalization for digit sequence
            norm_digits = raw_digits.translate(str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "|": "1"}))
            cleaned = re.sub(r"\s+", "", norm_digits)
            if re.fullmatch(r"\d{8,14}", cleaned):
                candidates.append(
                    UIDCandidate(
                        uid=cleaned,
                        confidence=obs.confidence,
                        source_id=source_id,
                        raw_text=text,
                        box=obs.box,
                        has_label=True,
                        roi_name=roi_name,
                    )
                )

    # 2. Adjacent split-box extraction (Box 1 has 'UID', Box 2 has digits)
    for obs1 in observations:
        text1 = obs1.text.strip()
        if not re.fullmatch(r"U?[I1l|]D\s*[:：\-]?", text1, re.IGNORECASE):
            continue
        if not obs1.box or len(obs1.box) < 4:
            continue

        right1 = max(p[0] for p in obs1.box)
        cy1 = sum(p[1] for p in obs1.box) / len(obs1.box)
        height1 = max(p[1] for p in obs1.box) - min(p[1] for p in obs1.box)

        for obs2 in observations:
            if obs2 is obs1 or not obs2.box or len(obs2.box) < 4:
                continue

            raw2 = obs2.text.strip()
            norm2 = raw2.translate(str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "|": "1"}))
            cleaned2 = re.sub(r"\s+", "", norm2)
            if not re.fullmatch(r"\d{8,14}", cleaned2):
                continue

            left2 = min(p[0] for p in obs2.box)
            cy2 = sum(p[1] for p in obs2.box) / len(obs2.box)

            # Spatial adjacency check: horizontal gap and vertical center alignment
            h_gap = left2 - right1
            v_gap = abs(cy2 - cy1)
            max_h_gap = max(40.0, height1 * 4.5)
            max_v_gap = max(10.0, height1 * 0.85)

            if -5.0 <= h_gap <= max_h_gap and v_gap <= max_v_gap:
                combined_conf = min(obs1.confidence, obs2.confidence)
                candidates.append(
                    UIDCandidate(
                        uid=cleaned2,
                        confidence=combined_conf,
                        source_id=source_id,
                        raw_text=f"{text1} {raw2}",
                        box=obs2.box,
                        has_label=True,
                        roi_name=f"{roi_name}_split",
                    )
                )

    return candidates
