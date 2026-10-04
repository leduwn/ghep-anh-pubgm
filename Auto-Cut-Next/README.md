# Auto-Cut-Next

Next-Generation PUBG Mobile Asset Extraction and PSD Compositing Suite.

## 1. Overview & Architecture

Auto-Cut-Next unites automatic screen classification, specialized item extraction, OCR, session state, and editable Photoshop PSD generation into a unified, modular architecture.

```text
RAW SCREENSHOT
      ↓
INGEST & VALIDATION (SHA-256, Unicode safe)
      ↓
SCREEN CLASSIFIER (Confidence & reasons)
      ↓
DEDICATED DETECTORS (Gun, Vehicle, Outfit, Equipment)
      ↓
GENERIC GRID FALLBACK (Row/col detection, aspect filtering)
      ↓
FILTERS (Lock detection, empty check, partial card rejection, dedup)
      ↓
CASCADE OCR ENGINE (Level, weapon name, UID)
      ↓
REVIEW QUEUE (Exceptions only, manual overrides)
      ↓
ACCOUNT SESSION (JSON manifest, atomic filesystem writes)
      ↓
ADAPTIVE LAYOUT ENGINE (Aspect preservation, uniform scaling)
      ↓
LIVE PREVIEW / INTERACTIVE EDITOR
      ↓
PHOTOSHOP BRIDGE (Editable Smart Objects, structured layer groups)
```

## 2. Directory Structure

```text
Auto-Cut-Next/
├── app/
│   ├── __init__.py
│   └── pipeline.py           # Central pipeline orchestrator
├── core/
│   ├── __init__.py
│   ├── constants.py          # Enums, versions, categories, thresholds
│   ├── exceptions.py         # Custom exception hierarchy
│   ├── models.py             # Rect, SourceImage, DetectedAsset, AccountSession
│   ├── settings.py           # AutoCutSettings model & validation
│   ├── session.py            # WorkspaceManager & atomic session persistence
│   ├── ingest.py             # Unicode-safe image decode, hashing, thumbnails
│   ├── cache.py              # LRUCache & DiskCache interfaces
│   ├── logging.py            # Structured stage logger with file rotation
│   └── metrics.py            # Performance timer and counters
├── detectors/                # Dedicated and generic grid card extractors
├── ocr/                      # Cascade EasyOCR engine (GPU/CPU fallback)
├── layout/                   # Adaptive grid layout and placement calculations
├── photoshop/                # JSX generator and Photoshop bridge
├── ui/                       # Interactive user interface
├── config/
│   └── default_settings.json # Base settings template
├── tests/                    # Comprehensive pytest unit & integration tests
├── README.md
└── run.py                    # Command-line entry point & diagnostics
```

## 3. Data Models & Session Manifest

- **SourceImage**: Unique per screenshot (SHA-256). Duplicate uploads with matching hashes are skipped incrementally.
- **DetectedAsset**: Logical asset representing a cropped item, bounding box (`Rect`), category, metadata, and quality flags (`locked`, `empty`, `partial`, `duplicate`).
- **AccountSession**: Single source of truth stored at `workspace/<account>/session.json`. Written using atomic `write -> flush -> fsync -> replace` to prevent data corruption.
- **Subsystem Versioning**: Each component has its own version string (`CLASSIFIER_VERSION`, `GUN_DETECTOR_VERSION`, etc.) for fine-grained cache invalidation.

## 4. Installation & Requirements

Ensure dependencies are installed:
```bash
pip install opencv-python pillow numpy easyocr pytest
```

## 5. Running & Testing

### Diagnostic Self-Test:
```bash
python Auto-Cut-Next/run.py --self-test
```

### Ingesting Screenshots:
```bash
python Auto-Cut-Next/run.py ingest <ACCOUNT_ID> <PATH_TO_SCREENSHOT_FOLDER>
```

### Classifying Screenshot Screens:
```bash
python Auto-Cut-Next/run.py classify <ACCOUNT_ID> [--force] [--json]
```

### Detecting Cards & Inventory Grids:
```bash
python Auto-Cut-Next/run.py detect <ACCOUNT_ID> [--force] [--json] [--verbose]
```

### Viewing Account Session Info:
```bash
python Auto-Cut-Next/run.py info <ACCOUNT_ID>
```

### Running Benchmarks:
```bash
python Auto-Cut-Next/scripts/benchmark_classifier.py
python Auto-Cut-Next/scripts/benchmark_detector.py
```

### Running Test Suite:
```bash
python -m pytest Auto-Cut-Next/tests -v
```

## 6. Milestone Status

- **Milestone 1 — Foundation**: Completed (Models, Settings, Logging, Caching, Ingest, Atomic Session, CLI Self-Test).
- **Milestone 2 — Robust Screen Classification Engine**: Completed.
  - `ClassificationContext`: Single decode, scan downscaling (1600 px max), lazy cached gray/hsv/masks, clamped ROI slicing.
  - Signal System: Strict/relaxed vertical blue indicators, Gun Lab anchors (header, orange badge, dark center), wardrobe layout rhythm and subtab rail smoothness, backpack 3-level selector, item detail popup frame, accessory separators and emote silhouettes, supercar template matching and lobby anchors.
  - Canonical Category Mapping: 12 standard categories (`GUN`, `VEHICLE`, `OUTFIT`, `ITEM_SET`, `HELMET`, `BACKPACK`, `MASK`, `GRENADE`, `PARACHUTE`, `EMOTE`, `MISC`, `OTHER`).
  - Strict Rules: Normal gun inventory tab is NEVER classified as GUN (only Gun Lab); Backpack requires 3-level selector; Item Set requires detail popup frame.
  - Decision Policy: `AUTO_ACCEPT` (score >= 0.85), `REVIEW` (0.55 <= score < 0.85 or ambiguity margin < 0.10), `UNKNOWN` (score < 0.55), `ERROR`.
  - Session Persistence: Results stored directly under `session.classifications`, versioned (`CLASSIFIER_VERSION = 2.0.0`), invalidated upon force ingest.
  - Microbenchmark: ~25 ms classify compute / ~38 ms end-to-end per 1080p source.
- **Milestone 3 — Generic Detector Core & Card Quality Pipeline**: Completed.
  - `VisionContext` & `DetectionContext`: Unified single-decode scan downsampling (1600px max) with exact coordinate projection between scan space and full-resolution space.
  - `CardGeometryProfile`: Configurable aspect ratio (0.60–1.30), size constraints, spacing ratios (0.85–1.35), border insets, and deterministic SHA-256 fingerprint for cache invalidation.
  - `GenericGridDetector`: Morphological contrast segmentation, connected components, coherent multi-row/multi-column grid reconstruction, regular spacing validation, single-card fallback, and adaptive border trimming.
  - `CardQualityEvaluator`: Corner binary lock template matching (`lock_mask.png`, IoU >= 0.50), central high-frequency detail analysis for empty slot detection, partial card aspect degradation scoring, and review uncertainty thresholds.
  - `AccountDeduplicator`: 64-bit 2D DCT perceptual hashing (pHash) with fast shortlist filtering and normalized MAE verification; category-scoped, deterministic account-level deduplication preserving canonical first-seen assets.
  - Pipeline & Orchestration: `pipeline.detect_session` with disk caching (`MISC_GRID_VERSION = 3.0.0`), category gating (eligible: `ITEM_SET`, `HELMET`, `BACKPACK`, `MASK`, `GRENADE`, `PARACHUTE`, `EMOTE`, `MISC`; deferred to M4: `GUN`, `VEHICLE`, `OUTFIT`), periodic session checkpointing, and CLI `detect` command.
  - Test Coverage & Performance: Comprehensive pytest suite across models, quality, dedup, grid reconstruction, and pipeline persistence; microbenchmark achieving ~69 ms end-to-end per 2778x1284 native screen.
- **Milestone 4 — Specialized Detectors**: Planned (Gun Lab layout & level badge, Vehicle grid & ceiling mask, Outfit VIP/Mythic).
- **Milestone 4 — Specialized Detectors**: Planned.
- **Milestone 5 — Cascade OCR**: Planned.
- **Milestone 6 — Review System**: Planned.
- **Milestone 7 — Layout Engine**: Planned.
- **Milestone 8 — Preview & Editor**: Planned.
- **Milestone 9 — Photoshop Bridge & PSD Export**: Planned.
- **Milestone 10 — Profiling & Performance**: Planned.
- **Milestone 11 — Packaging**: Planned.
