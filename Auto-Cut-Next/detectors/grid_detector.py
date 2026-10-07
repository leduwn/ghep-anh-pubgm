"""Generic inventory card grid detector with candidate discovery and dynamic reconstruction."""

from __future__ import annotations

import time
from typing import Optional

import cv2
import numpy as np

from core.constants import MISC_GRID_VERSION
from core.models import Rect
from .detection_context import DetectionContext
from .detector_models import CardGeometryProfile, CardCandidate, GridDetectionResult
from .card_quality import CardQualityEvaluator


class GenericGridDetector:
    """Detects inventory tile grids and individual cards using morphological contrast extraction."""

    NAME = "generic_grid_detector"
    VERSION = MISC_GRID_VERSION

    def __init__(
        self,
        default_profile: Optional[CardGeometryProfile] = None,
        quality_evaluator: Optional[CardQualityEvaluator] = None,
    ):
        self.profile = default_profile or CardGeometryProfile()
        self.quality_evaluator = quality_evaluator or CardQualityEvaluator()

    def discover_candidates(
        self,
        context: DetectionContext,
        profile: CardGeometryProfile,
        search_roi: Optional[Rect] = None,
    ) -> list[Rect]:
        """Discovers rectangular candidate card components using contrast morphology."""
        scan_full = context.scan_bgr
        full_h, full_w = context.scan_h, context.scan_w
        if full_h < 20 or full_w < 20:
            return []

        if search_roi is not None:
            roi_x = max(0, min(full_w - 1, int(search_roi.x)))
            roi_y = max(0, min(full_h - 1, int(search_roi.y)))
            roi_w = max(1, min(full_w - roi_x, int(search_roi.w)))
            roi_h = max(1, min(full_h - roi_y, int(search_roi.h)))
            scan = scan_full[roi_y : roi_y + roi_h, roi_x : roi_x + roi_w]
        else:
            roi_x, roi_y = 0, 0
            scan = scan_full

        h, w = scan.shape[:2]
        if h < 20 or w < 20:
            return []

        gray = cv2.cvtColor(scan, cv2.COLOR_BGR2GRAY)
        med_val = float(np.median(gray))

        # Scaled odd kernel for morphology to protect thin borders
        k_size = 3
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_size, k_size))

        if med_val > 110:
            # Light background -> cards are dark/contrasting tiles
            min_c = np.min(scan, axis=2)
            max_c = np.max(scan, axis=2)
            spread = max_c.astype(np.int16) - min_c.astype(np.int16)
            dark = (min_c < 100) & ((max_c < 150) | (spread > 40))
            dark_u8 = (dark.astype(np.uint8)) * 255
            closed = cv2.morphologyEx(dark_u8, cv2.MORPH_CLOSE, kernel)
        else:
            # Dark background -> cards, fills, and/or borders are brighter than background
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
            # Fill external contours so hollow borders become solid candidate regions
            contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            filled = np.zeros_like(closed)
            for cnt in contours:
                cv2.drawContours(filled, [cnt], -1, 255, -1)
            closed = filled

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
        candidates: list[Rect] = []

        min_w = full_w * profile.relative_width_min
        max_w = full_w * profile.relative_width_max
        min_h = full_h * profile.relative_height_min
        max_h = full_h * profile.relative_height_max

        for idx in range(1, num_labels):
            x, y, cw, ch, area = stats[idx]
            if not (min_w <= cw <= max_w) or not (min_h <= ch <= max_h):
                continue

            aspect = float(cw) / float(max(1, ch))
            if not (profile.aspect_min <= aspect <= profile.aspect_max):
                continue

            # Fill ratio check inside bounding box
            fill_ratio = float(area) / float(max(1, cw * ch))
            if fill_ratio < 0.60:
                continue

            candidates.append(Rect(x + roi_x, y + roi_y, cw, ch))

        return candidates

    def reconstruct_grid(
        self,
        candidates: list[Rect],
        profile: CardGeometryProfile,
        scan_w: int,
        scan_h: int,
    ) -> list[tuple[Rect, int, int]]:
        """Reconstructs coherent rows and columns from unstructured candidate rectangles."""
        if not candidates:
            return []

        grids = []
        for anchor in candidates:
            aw, ah = anchor.w, anchor.h
            similar = [c for c in candidates if (0.84 < (c.w / float(max(1, aw))) < 1.19) and (0.84 < (c.h / float(max(1, ah))) < 1.19)]

            # Top row candidates aligned horizontally with anchor
            first_row_cands = sorted(
                [c for c in similar if abs(c.y - anchor.y) < ah * 0.08],
                key=lambda r: r.x,
            )

            # Try groups starting at each candidate in the first row
            for start_idx in range(len(first_row_cands) - 1):
                top = [first_row_cands[start_idx]]
                expected_step = None
                for next_cand in first_row_cands[start_idx + 1:]:
                    curr_step = (next_cand.x + next_cand.w / 2.0) - (top[-1].x + top[-1].w / 2.0)
                    if not (aw * profile.spacing_min_ratio < curr_step < aw * profile.spacing_max_ratio):
                        break
                    if expected_step is not None and abs(curr_step - expected_step) > aw * 0.10:
                        break
                    expected_step = curr_step
                    top.append(next_cand)

                if len(top) < 2:
                    continue
                centers = [r.x + r.w / 2.0 for r in top]

                # Match subsequent row cards aligned to column centers
                selected = []
                for r in similar:
                    center_x = r.x + r.w / 2.0
                    col_diffs = [abs(center_x - c_x) for c_x in centers]
                    best_col = int(np.argmin(col_diffs))
                    if col_diffs[best_col] > aw * 0.10 or r.y < anchor.y - ah * 0.08:
                        continue
                    selected.append((r, best_col))

                # Group selected cards into rows by vertical proximity
                rows: list[list[tuple[Rect, int]]] = []
                for r, col in sorted(selected, key=lambda item: item[0].y):
                    matched_row = next((row for row in rows if abs(row[0][0].y - r.y) < ah * 0.08), None)
                    if matched_row is None:
                        rows.append([(r, col)])
                    else:
                        matched_row.append((r, col))

                # Check vertical row spacing regularity if multiple rows
                if len(rows) > 1:
                    row_dys = [rows[i + 1][0][0].y - rows[i][0][0].y for i in range(len(rows) - 1)]
                    if not all(ah * profile.spacing_min_ratio < dy < ah * profile.spacing_max_ratio for dy in row_dys):
                        continue

                # Flatten ordered cards with (row_idx, col_idx)
                ordered: list[tuple[Rect, int, int]] = []
                for row_idx, row_items in enumerate(rows):
                    for r, col_idx in sorted(row_items, key=lambda item: item[1]):
                        ordered.append((r, row_idx, col_idx))

                if ordered:
                    grids.append((len(ordered), -anchor.y, ordered))

        # Single large tile fallback
        if not grids and profile.allow_single:
            large_singles = [
                c for c in candidates
                if (c.w * c.h > scan_w * scan_h * 0.18) or (c.w > scan_w * 0.30 and c.h > scan_h * 0.30)
            ]
            if large_singles:
                best_single = max(large_singles, key=lambda r: r.w * r.h)
                grids.append((1, -best_single.y, [(best_single, 0, 0)]))

        if not grids:
            return []

        best_grid = max(grids, key=lambda g: (g[0], g[1]))
        return best_grid[2]

    def compute_grid_confidence(
        self,
        ordered_grid: list[tuple[Rect, int, int]],
        scan_w: int,
        scan_h: int,
        profile: CardGeometryProfile,
    ) -> tuple[float, dict[str, Any]]:
        """Calculates geometry-based confidence score and diagnostic indicators."""
        if not ordered_grid:
            return 0.0, {
                "size_consistency": 0.0,
                "horizontal_alignment": 0.0,
                "vertical_alignment": 0.0,
                "spacing_consistency": 0.0,
                "candidate_count": 0,
                "fill_ratio": 0.0,
            }

        # Case 1: Single tile
        if len(ordered_grid) == 1:
            r = ordered_grid[0][0]
            aspect = float(r.w) / max(1.0, float(r.h))
            aspect_dev = abs(aspect - 1.0)
            aspect_score = 1.0 if aspect_dev <= 0.10 else max(0.0, 1.0 - (aspect_dev - 0.10) * 2.0)

            area_ratio = (r.w * r.h) / max(1.0, float(scan_w * scan_h))
            if 0.18 <= area_ratio <= 0.65:
                area_score = 1.0
            elif area_ratio < 0.18:
                area_score = max(0.0, area_ratio / 0.18)
            else:
                area_score = max(0.0, 1.0 - (area_ratio - 0.65) / 0.35)

            min_margin = min(r.x, r.y, max(0, scan_w - r.right), max(0, scan_h - r.bottom))
            clearance_score = 1.0 if min_margin >= 20 else max(0.0, float(min_margin) / 20.0)

            single_conf = round(0.40 * area_score + 0.35 * aspect_score + 0.25 * clearance_score, 4)
            diag = {
                "size_consistency": 1.0,
                "horizontal_alignment": 1.0,
                "vertical_alignment": 1.0,
                "spacing_consistency": 1.0,
                "candidate_count": 1,
                "fill_ratio": 1.0,
                "aspect_match": round(aspect_score, 4),
                "area_score": round(area_score, 4),
                "edge_clearance": round(clearance_score, 4),
            }
            return single_conf, diag

        # Case 2: Multi-card grid (>= 2 candidates)
        widths = [r.w for r, _, _ in ordered_grid]
        heights = [r.h for r, _, _ in ordered_grid]
        med_w = float(np.median(widths))
        med_h = float(np.median(heights))

        # Size consistency
        std_w = float(np.std(widths))
        std_h = float(np.std(heights))
        w_score = max(0.0, 1.0 - 2.0 * (std_w / max(1.0, med_w)))
        h_score = max(0.0, 1.0 - 2.0 * (std_h / max(1.0, med_h)))
        size_consistency = round((w_score + h_score) / 2.0, 4)

        # Horizontal alignment (row alignment)
        rows_dict: dict[int, list[Rect]] = {}
        cols_dict: dict[int, list[Rect]] = {}
        for r, r_idx, c_idx in ordered_grid:
            rows_dict.setdefault(r_idx, []).append(r)
            cols_dict.setdefault(c_idx, []).append(r)

        row_scores = []
        for r_idx, cards in rows_dict.items():
            if len(cards) >= 2:
                y_centers = [c.y + c.h / 2.0 for c in cards]
                std_y = float(np.std(y_centers))
                score = max(0.0, 1.0 - (std_y / max(1.0, med_h * 0.15)))
                row_scores.append(score)
        horizontal_alignment = round(float(np.mean(row_scores)), 4) if row_scores else 1.0

        # Vertical alignment (column alignment)
        col_scores = []
        for c_idx, cards in cols_dict.items():
            if len(cards) >= 2:
                x_centers = [c.x + c.w / 2.0 for c in cards]
                std_x = float(np.std(x_centers))
                score = max(0.0, 1.0 - (std_x / max(1.0, med_w * 0.15)))
                col_scores.append(score)
        vertical_alignment = round(float(np.mean(col_scores)), 4) if col_scores else 1.0

        # Spacing consistency
        h_steps = []
        for r_idx, cards in rows_dict.items():
            if len(cards) >= 2:
                sorted_c = sorted(cards, key=lambda c: c.x)
                for i in range(len(sorted_c) - 1):
                    h_steps.append((sorted_c[i + 1].x + sorted_c[i + 1].w / 2.0) - (sorted_c[i].x + sorted_c[i].w / 2.0))

        v_steps = []
        for c_idx, cards in cols_dict.items():
            if len(cards) >= 2:
                sorted_c = sorted(cards, key=lambda c: c.y)
                for i in range(len(sorted_c) - 1):
                    v_steps.append((sorted_c[i + 1].y + sorted_c[i + 1].h / 2.0) - (sorted_c[i].y + sorted_c[i].h / 2.0))

        h_spacing_score = 1.0
        if len(h_steps) >= 2:
            med_step = float(np.median(h_steps))
            std_step = float(np.std(h_steps))
            h_spacing_score = max(0.0, 1.0 - 3.0 * (std_step / max(1.0, med_step)))

        v_spacing_score = 1.0
        if len(v_steps) >= 2:
            med_step = float(np.median(v_steps))
            std_step = float(np.std(v_steps))
            v_spacing_score = max(0.0, 1.0 - 3.0 * (std_step / max(1.0, med_step)))

        if len(h_steps) >= 2 and len(v_steps) >= 2:
            spacing_consistency = round((h_spacing_score + v_spacing_score) / 2.0, 4)
        elif len(h_steps) >= 2:
            spacing_consistency = round(h_spacing_score, 4)
        elif len(v_steps) >= 2:
            spacing_consistency = round(v_spacing_score, 4)
        else:
            spacing_consistency = 1.0

        # Fill ratio
        max_r = max(r_idx for _, r_idx, _ in ordered_grid) + 1
        max_c = max(c_idx for _, _, c_idx in ordered_grid) + 1
        expected_cells = max_r * max_c
        fill_ratio = round(min(1.0, len(ordered_grid) / float(expected_cells)), 4)

        grid_conf = round(
            0.25 * size_consistency +
            0.20 * horizontal_alignment +
            0.20 * vertical_alignment +
            0.25 * spacing_consistency +
            0.10 * fill_ratio,
            4
        )

        diag = {
            "size_consistency": size_consistency,
            "horizontal_alignment": horizontal_alignment,
            "vertical_alignment": vertical_alignment,
            "spacing_consistency": spacing_consistency,
            "candidate_count": len(ordered_grid),
            "fill_ratio": fill_ratio,
        }
        return grid_conf, diag

    def detect(
        self,
        context: DetectionContext,
        profile: Optional[CardGeometryProfile] = None,
    ) -> GridDetectionResult:
        """Executes full detection pipeline: discovery, reconstruction, and quality evaluation."""
        t0 = time.perf_counter()
        active_profile = profile or self.profile

        candidates_rects = self.discover_candidates(context, active_profile)
        ordered_grid = self.reconstruct_grid(candidates_rects, active_profile, context.scan_w, context.scan_h)

        if not ordered_grid:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return GridDetectionResult(
                detected=False,
                grid_confidence=0.0,
                rows=0,
                columns=0,
                candidates=[],
                accepted=[],
                rejected=[],
                diagnostics={"raw_candidates_count": len(candidates_rects)},
                duration_ms=round(duration_ms, 2),
            )

        median_w = float(np.median([r.w for r, _, _ in ordered_grid]))
        median_h = float(np.percentile([r.h for r, _, _ in ordered_grid], 65))

        all_candidates: list[CardCandidate] = []
        accepted_candidates: list[CardCandidate] = []
        rejected_candidates: list[CardCandidate] = []

        max_row = max(r_idx for _, r_idx, _ in ordered_grid) + 1
        max_col = max(c_idx for _, _, c_idx in ordered_grid) + 1

        for r_scan, row_idx, col_idx in ordered_grid:
            partial_score = 0.0
            if r_scan.w < median_w * 0.95 or r_scan.h < median_h * 0.95:
                ratio = min(float(r_scan.w) / max(1.0, median_w), float(r_scan.h) / max(1.0, median_h))
                partial_score = max(0.0, 1.0 - ratio)

            # Border trimming
            trim_x = max(0, int(round((r_scan.w - median_w) / 2.0)))
            trim_y = max(0, int(round((r_scan.h - median_h) / 2.0)))
            trimmed_scan = Rect(
                r_scan.x + trim_x,
                r_scan.y + trim_y,
                max(1, r_scan.w - 2 * trim_x),
                max(1, r_scan.h - 2 * trim_y),
            )

            # Content inset
            inset_px = max(1, int(round(min(trimmed_scan.w, trimmed_scan.h) * active_profile.border_inset_ratio)))
            content_scan = Rect(
                trimmed_scan.x + inset_px,
                trimmed_scan.y + inset_px,
                max(1, trimmed_scan.w - 2 * inset_px),
                max(1, trimmed_scan.h - 2 * inset_px),
            )

            raw_orig = context.scan_to_original_rect(trimmed_scan)
            content_orig = context.scan_to_original_rect(content_scan)

            tile_bgr = context.crop_original(content_orig)
            quality_res = self.quality_evaluator.evaluate(tile_bgr, partial_score=partial_score)

            candidate = CardCandidate(
                rect_scan=trimmed_scan,
                rect_original=raw_orig,
                content_rect_original=content_orig,
                geometry_score=round(1.0 - partial_score, 4),
                row=row_idx,
                column=col_idx,
                partial_score=quality_res.partial_score,
                lock_score=quality_res.lock_score,
                content_score=quality_res.content_score,
                locked=quality_res.locked,
                empty=quality_res.empty,
                partial=quality_res.partial,
                confidence=quality_res.confidence,
                review_required=quality_res.review_required,
                rejection_reasons=quality_res.reasons,
                diagnostics=quality_res.diagnostics,
            )

            all_candidates.append(candidate)
            if candidate.locked or candidate.empty or candidate.partial:
                rejected_candidates.append(candidate)
            else:
                accepted_candidates.append(candidate)

        duration_ms = (time.perf_counter() - t0) * 1000.0
        grid_conf, geom_diag = self.compute_grid_confidence(
            ordered_grid,
            scan_w=context.scan_w,
            scan_h=context.scan_h,
            profile=active_profile,
        )

        diagnostics = {
            "median_w": median_w,
            "median_h": median_h,
            "raw_candidates_count": len(candidates_rects),
            **geom_diag,
        }

        return GridDetectionResult(
            detected=True,
            grid_confidence=grid_conf,
            rows=max_row,
            columns=max_col,
            candidates=all_candidates,
            accepted=accepted_candidates,
            rejected=rejected_candidates,
            diagnostics=diagnostics,
            duration_ms=round(duration_ms, 2),
        )


