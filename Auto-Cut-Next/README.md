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

### Viewing Account Session Info:
```bash
python Auto-Cut-Next/run.py info <ACCOUNT_ID>
```

### Running Test Suite:
```bash
python -m pytest Auto-Cut-Next/tests -v
```

## 6. Milestone Status

- **Milestone 1 — Foundation**: Completed (Models, Settings, Logging, Caching, Ingest, Atomic Session, CLI Self-Test, 34/34 tests passing).
- **Milestone 2 — Classification**: Planned.
- **Milestone 3 — Detector Core**: Planned.
- **Milestone 4 — Specialized Detectors**: Planned.
- **Milestone 5 — Cascade OCR**: Planned.
- **Milestone 6 — Review System**: Planned.
- **Milestone 7 — Layout Engine**: Planned.
- **Milestone 8 — Preview & Editor**: Planned.
- **Milestone 9 — Photoshop Bridge & PSD Export**: Planned.
- **Milestone 10 — Profiling & Performance**: Planned.
- **Milestone 11 — Packaging**: Planned.
