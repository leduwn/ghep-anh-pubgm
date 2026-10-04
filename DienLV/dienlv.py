import argparse, hashlib, json, os, platform, random, re, shutil, string, subprocess, sys, ssl, warnings

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import cv2
ssl._create_default_https_context = ssl._create_unverified_context
import easyocr
import easyocr.config as easyocr_config
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pytoshop import enums, image_data
from pytoshop.user import nested_layers

try:
    import requests
except ImportError:
    requests = None

IMAGE_EXTENSIONS = {".jpg", ".png", ".jpeg"}
APP_NAME = "DienLV"
APP_VERSION = "1.3.4"
LICENSE_API_URL = os.getenv("DIENLV_LICENSE_API_URL", "https://script.google.com/macros/s/AKfycbxpISaYGuIkaJemkq9_znDFAV2OaMFyzi_6O3cg1zpcZOaT7MNenQBU2DLFbZNwjwKA/exec")
LICENSE_API_TOKEN = os.getenv("DIENLV_LICENSE_API_TOKEN", "")
LICENSE_CHECK_INTERVAL_DAYS = 7
LICENSE_OFFLINE_GRACE_DAYS = 3
EASY_OCR_LANGS = ["vi", "en"]
EASY_OCR_DETECT_NETWORK = "craft"
EASY_OCR_RECOG_MODEL = "latin_g2"
EASY_OCR_READER = None

def app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

def resource_dir():
    bundled_dir = getattr(sys, "_MEIPASS", None)
    if bundled_dir:
        return Path(bundled_dir)
    return Path(__file__).resolve().parent

APP_DIR = app_dir()
RESOURCE_DIR = resource_dir()
DEFAULT_FONT_PATH = RESOURCE_DIR / "assets" / "itc.ttf"
INPUT_DIR = APP_DIR / "input"
CROP_OUTPUT_DIR = APP_DIR / "anhle"
TRASH_DIR = APP_DIR / "anhrac"
CONFIG_PATH = APP_DIR / "config.json"
FINAL_FILENAME_PATTERN = re.compile("^[A-Z0-9]{10}$")
RIGHT_RATIO = 0.6
CROP_INNER = 6
ORANGE_LOWER = (5, 120, 120)
ORANGE_UPPER = (30, 255, 255)
MORPH_KERNEL_SIZE = 3
MIN_AREA = 20_000
IMAGES_PER_COLUMN = 0
WORKERS = 8
OCR_BATCH_SIZE = 16
OCR_WORKERS = 0
SORT_GUNS = True
ROW_RESIZE_PCT = 8
LEVEL_CROP_HEIGHT_RATIO = 0.18
LEVEL_CROP_WIDTH_RATIO = 0.76
FAST_LEVEL_X_START_RATIO = 0.0
FAST_LEVEL_X_END_RATIO = 0.25
FAST_LEVEL_Y_START_RATIO = 0.08
FAST_LEVEL_Y_END_RATIO = 0.20
LEVEL_TITLE_BOX = (0.0, 0.92, 0.0, 0.42)
LEVEL_PROGRESS_BOX = (0.0, 0.53, 0.53, 0.85)

DEFAULT_CONFIG = {
    "license_key": "",
    "machine_id": "",
    "last_success_at": "",
    "font_path": "",
    "photoshop_font_ps_name": "ArialMT",
    "level_left_px": 7,
    "level_bottom_px": 12,
    "maxfilter_thickness": 1,
    "minfilter_thickness": ""
}

def read_image(file_path):
    try:
        data = np.fromfile(str(file_path), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is not None:
            return img
    except Exception:
        pass
    return cv2.imread(str(file_path))

def write_image(file_path, img):
    try:
        ext = Path(file_path).suffix or ".png"
        success, encoded = cv2.imencode(ext, img)
        if success:
            encoded.tofile(str(file_path))
            return True
    except Exception:
        pass
    return cv2.imwrite(str(file_path), img)

def get_special_gun_asset(filename: str) -> Path:
    candidates = [
        RESOURCE_DIR / "assets" / "gun" / filename,
        APP_DIR / "assets" / "gun" / filename,
        APP_DIR / ".internal" / "assets" / "gun" / filename,
        Path(__file__).resolve().parent / "assets" / "gun" / filename,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return RESOURCE_DIR / "assets" / "gun" / filename

SPECIAL_GUNS = {
    "akm_hoanguc": {"label": "AKM Hoả Ngục", "asset": get_special_gun_asset("akmhoanguc.png")},
    "ump_sinhnhat": {"label": "UMP Sinh Nhật", "asset": get_special_gun_asset("umpsinhnhat.png")}
}
SPECIAL_GUN_CHOICES = {"1": ["akm_hoanguc"], "2": ["ump_sinhnhat"], "3": ["akm_hoanguc", "ump_sinhnhat"]}

warnings.filterwarnings("ignore", message=".*'pin_memory' argument is set as true but.*", category=UserWarning)
warnings.filterwarnings("ignore", category=UserWarning)

@dataclass
class ProcessedImage:
    index: int
    file_name: str
    crop: np.ndarray
    gun_crop: np.ndarray
    level_layer: Optional[np.ndarray] = None
    level: Optional[int] = None
    ocr_text: str = ""
    background_color: Optional[str] = None
    converted_3_3_level4: bool = False
    special_type: Optional[str] = None
    special_insert_position: Optional[int] = None
    counter_crop: Optional[np.ndarray] = None

@dataclass
class ImageCandidate:
    index: int
    file_name: str
    crop: np.ndarray
    fast_level_area: np.ndarray
    level_area: np.ndarray
    counter_crop: Optional[np.ndarray] = None

@dataclass
class GridLayoutItem:
    processed: ProcessedImage
    crop: np.ndarray
    gun_crop: np.ndarray
    level_layer: Optional[np.ndarray]
    x: int
    y: int
    width: int
    height: int

def utc_now():
    return datetime.now(timezone.utc)

def parse_utc_datetime(value):
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        normalized = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)

def license_api_configured():
    try:
        parsed = urlparse(LICENSE_API_URL)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False

def easyocr_model_dir():
    return Path(str(easyocr_config.MODULE_PATH)) / "model"

def easyocr_required_model_paths():
    model_dir = easyocr_model_dir()
    detector = easyocr_config.detection_models[EASY_OCR_DETECT_NETWORK]["filename"]
    recognizer = easyocr_config.recognition_models["gen2"][EASY_OCR_RECOG_MODEL]["filename"]
    return [model_dir / detector, model_dir / recognizer]

def easyocr_models_ready():
    return all(path.is_file() for path in easyocr_required_model_paths())

def first_time_setup_needed():
    return not easyocr_models_ready()

def print_setup_header():
    print("=" * 64, flush=True)
    print(" LẦN ĐẦU KHỞI CHẠY DIENLV", flush=True)
    print(" Ứng dụng đang tải model EasyOCR về máy.", flush=True)
    print(" Quá trình này chỉ chạy một lần và phụ thuộc vào tốc độ mạng.", flush=True)
    print("=" * 64, flush=True)
    print("", flush=True)

def get_easyocr_reader(show_setup=False):
    global EASY_OCR_READER
    if EASY_OCR_READER is not None:
        return EASY_OCR_READER
    if show_setup:
        print_setup_header()
        print(f"Thư mục model: {easyocr_model_dir()}", flush=True)
        print("Đang kiểm tra và tải model EasyOCR nếu còn thiếu...", flush=True)
        print("Vui lòng đợi, app vẫn đang hoạt động.", flush=True)
        print("", flush=True)
    try:
        try:
            EASY_OCR_READER = easyocr.Reader(EASY_OCR_LANGS, gpu=False, verbose=False, download_enabled=False)
        except (TypeError, Exception):
            EASY_OCR_READER = easyocr.Reader(EASY_OCR_LANGS, gpu=False, verbose=False)
        if show_setup:
            print("", flush=True)
            print("Setup EasyOCR hoàn tất.", flush=True)
            print("Đang chuyển sang bước kích hoạt license...", flush=True)
            print("", flush=True)
        return EASY_OCR_READER
    except Exception as exc:
        print()
        print("Không setup được model EasyOCR.")
        print("Vui lòng kiểm tra kết nối Internet rồi mở lại app.")
        print(f"Lỗi: {exc}")
        sys.exit(1)

def run_first_time_setup_if_needed():
    if first_time_setup_needed():
        get_easyocr_reader(show_setup=True)

def hash_machine_parts(parts):
    clean_parts = [str(part).strip() for part in parts if str(part).strip()]
    if not clean_parts:
        return ""
    raw = "|".join(clean_parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24].upper()

def read_windows_machine_guid():
    if platform.system().lower() != "windows":
        return ""
    cmd = 'reg query "HKLM\\SOFTWARE\\Microsoft\\Cryptography" /v MachineGuid'
    try:
        output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return ""
    for line in output.splitlines():
        if "MachineGuid" in line:
            parts = line.strip().split()
            if len(parts) >= 3:
                return parts[-1].strip()
    return ""

def get_machine_id():
    guid = read_windows_machine_guid()
    node = platform.node()
    system = platform.system()
    machine = platform.machine()
    processor = platform.processor()
    user = os.getenv("USERNAME") or os.getenv("USER") or ""
    parts = [guid, node, system, machine, processor, user]
    hashed = hash_machine_parts(parts)
    return hashed or "UNKNOWN_DEVICE"

def get_legacy_machine_id():
    node = platform.node()
    system = platform.system()
    machine = platform.machine()
    processor = platform.processor()
    user = os.getenv("USERNAME") or os.getenv("USER") or ""
    parts = [node, system, machine, processor, user]
    hashed = hash_machine_parts(parts)
    return hashed or "UNKNOWN_DEVICE"

def unique_values(values):
    seen = set()
    result = []
    for item in values:
        cleaned = str(item or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result

def load_json_file(path):
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def resolve_config_path(value, default_path):
    if not value or not str(value).strip():
        return default_path
    path = Path(str(value).strip())
    if not path.is_absolute():
        path = (APP_DIR / path).resolve()
    return path

def non_negative_int(value):
    try:
        int_value = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(f"'{value}' không phải số nguyên hợp lệ.") from exc
    if int_value < 0:
        raise argparse.ArgumentTypeError(f"Giá trị phải >= 0, nhận được {value}.")
    return int_value

def config_has_value(data, key):
    return key in data and data[key] is not None and str(data[key]).strip() != ""

def config_int(config, key, default, minimum=0):
    if not config_has_value(config, key):
        return default
    try:
        value = int(config[key])
        return max(minimum, value)
    except (TypeError, ValueError):
        return default

def optional_odd_filter_size(config, key):
    if not config_has_value(config, key):
        return None
    try:
        value = int(config[key])
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value if value % 2 == 1 else value + 1

def odd_filter_size(config, key, default):
    value = optional_odd_filter_size(config, key)
    if value is not None:
        return value
    return default if default % 2 == 1 else default + 1

def normalize_config(data):
    normalized = dict(DEFAULT_CONFIG)
    normalized.update(data)
    normalized["level_left_px"] = config_int(normalized, "level_left_px", DEFAULT_CONFIG["level_left_px"], minimum=0)
    normalized["level_bottom_px"] = config_int(normalized, "level_bottom_px", DEFAULT_CONFIG["level_bottom_px"], minimum=0)
    max_filter = optional_odd_filter_size(normalized, "maxfilter_thickness")
    min_filter = optional_odd_filter_size(normalized, "minfilter_thickness")
    if max_filter is not None and min_filter is not None:
        min_filter = None
    if max_filter is None and min_filter is None:
        max_filter = DEFAULT_CONFIG["maxfilter_thickness"]
    normalized["maxfilter_thickness"] = "" if max_filter is None else max_filter
    normalized["minfilter_thickness"] = "" if min_filter is None else min_filter
    return normalized

def load_config():
    return normalize_config(load_json_file(CONFIG_PATH))

def save_config(config):
    CONFIG_PATH.parent.mkdir(exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
        file.write("\n")

CONFIG = load_config()

def text_filter(config):
    max_size = optional_odd_filter_size(config, "maxfilter_thickness")
    if max_size and max_size > 1:
        return ImageFilter.MaxFilter(max_size)
    min_size = optional_odd_filter_size(config, "minfilter_thickness")
    if min_size and min_size > 1:
        return ImageFilter.MinFilter(min_size)
    return None

def load_license_cache():
    return load_config()

def save_license_cache(license_key, machine_id):
    config = load_config()
    config["license_key"] = license_key
    config["machine_id"] = machine_id
    config["last_success_at"] = utc_now().isoformat()
    save_config(config)

def cache_matches_machine(cache, machine_id):
    cached_machine_id = str(cache.get("machine_id", "")).strip()
    if not cached_machine_id:
        return False
    legacy_id = get_legacy_machine_id()
    return cached_machine_id in {machine_id, legacy_id}

def license_check_is_fresh(cache, machine_id):
    if not cache.get("license_key"):
        return False
    if not cache_matches_machine(cache, machine_id):
        return False
    last_success_at = parse_utc_datetime(cache.get("last_success_at"))
    return utc_now() - last_success_at <= timedelta(days=LICENSE_CHECK_INTERVAL_DAYS)

def offline_grace_is_valid(cache, machine_id):
    if not cache_matches_machine(cache, machine_id):
        return False
    last_success_at = parse_utc_datetime(cache.get("last_success_at"))
    return utc_now() - last_success_at <= timedelta(days=LICENSE_CHECK_INTERVAL_DAYS + LICENSE_OFFLINE_GRACE_DAYS)

def prompt_license_key(cache):
    cached_key = str(cache.get("license_key", "")).strip()
    if cached_key:
        return cached_key
    while True:
        print("Vui lòng nhập license để kích hoạt DienLV.")
        license_key = input("License: ").strip()
        if license_key:
            return license_key
        print("License không được để trống.")

def verify_license_online(license_key, machine_id, machine_ids):
    if requests is None:
        return (False, "Thiếu thư viện requests. Vui lòng chạy setup.cmd hoặc build lại app.")
    if not license_api_configured():
        return (False, "Chưa cấu hình LICENSE_API_URL trong dienlv.py.")
    payload = {"license_key": license_key, "machine_id": machine_id, "app_name": APP_NAME, "app_version": APP_VERSION}
    if machine_ids:
        payload["machine_ids"] = machine_ids
    if LICENSE_API_TOKEN:
        payload["token"] = LICENSE_API_TOKEN
    try:
        response = requests.post(LICENSE_API_URL, json=payload, timeout=20)
        response.raise_for_status()
        data = response.json()
        message = str(data.get("message") or "").strip()
        if data.get("ok") is True:
            if data.get("update_available") is True:
                latest_version = str(data.get("latest_version") or "").strip()
                release_note = str(data.get("release_note") or "").strip()
                update_message = f"Có bản cập nhật mới {latest_version}." if latest_version else "Có bản cập nhật mới."
                if release_note:
                    update_message = f"{update_message}\nNội dung: {release_note}"
                update_message = f"{update_message}\nĐóng DienLV rồi chạy updater.cmd để cập nhật."
                return (True, update_message)
            return (True, "")
        if not message:
            message = "License không hợp lệ."
        return (False, message)
    except requests.RequestException as exc:
        return (None, f"Không kết nối được máy chủ license: {exc}")
    except ValueError:
        return (False, "Máy chủ license trả về dữ liệu không hợp lệ.")

def require_valid_license():
    # Bỏ qua kiểm tra license_key để chạy trực tiếp không cần xác thực
    pass

def wait_before_exit():
    if not sys.stdin or not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
        return
    print()
    print("Nhấn phím bất kỳ để thoát...", flush=True)
    try:
        if platform.system().lower() == "windows":
            import msvcrt
            msvcrt.getch()
        else:
            input()
    except Exception:
        pass

FONT_CACHE = {}

def get_font_path():
    configured_path = CONFIG.get("font_path")
    font_path = resolve_config_path(configured_path, DEFAULT_FONT_PATH)
    if not font_path.exists():
        fallback_candidates = [
            APP_DIR / "assets" / "itc.ttf",
            APP_DIR / "standalone" / ".internal" / "itc.ttf",
            RESOURCE_DIR / "assets" / "itc.ttf",
            RESOURCE_DIR / "itc.ttf",
            Path(__file__).resolve().parent / "assets" / "itc.ttf",
        ]
        for candidate in fallback_candidates:
            if candidate.exists():
                return candidate
    return font_path

PRELOADED_LEVEL_BADGES = {}

def preload_fonts():
    font_path = get_font_path()
    if font_path.exists():
        for sz in range(65, 80):
            try:
                font = ImageFont.truetype(str(font_path), sz)
                FONT_CACHE[sz] = font
                for lvl in range(1, 9):
                    text = f"LV{lvl}"
                    left, top, right, bottom = font.getbbox(text)
                    img = Image.new("RGBA", (right + 4, bottom + 4), (0, 0, 0, 0))
                    draw = ImageDraw.Draw(img)
                    draw.text((0, 0), text, font=font, fill=(255, 255, 255, 255))
                    tf = text_filter(CONFIG)
                    if tf:
                        img = img.filter(tf)
                    cropped = img.crop((left, top, right, bottom))
                    PRELOADED_LEVEL_BADGES[(sz, lvl)] = (
                        np.array(cropped),
                        left,
                        top,
                        right,
                        bottom,
                        font
                    )
            except Exception:
                pass

def get_or_create_badge(font_size, level_value):
    key = (font_size, level_value)
    if key in PRELOADED_LEVEL_BADGES:
        return PRELOADED_LEVEL_BADGES[key]
    font = load_font(font_size)
    text = f"LV{level_value}"
    left, top, right, bottom = font.getbbox(text)
    img = Image.new("RGBA", (right + 4, bottom + 4), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((0, 0), text, font=font, fill=(255, 255, 255, 255))
    tf = text_filter(CONFIG)
    if tf:
        img = img.filter(tf)
    cropped = img.crop((left, top, right, bottom))
    info = (
        np.array(cropped),
        left,
        top,
        right,
        bottom,
        font
    )
    PRELOADED_LEVEL_BADGES[key] = info
    return info

def load_font(size):
    if size in FONT_CACHE:
        return FONT_CACHE[size]
    font_path = get_font_path()
    try:
        font = ImageFont.truetype(str(font_path), size)
        FONT_CACHE[size] = font
        return font
    except Exception as exc:
        print(f"Không tải được font: {font_path}")
        print(f"Lỗi: {exc}")
        sys.exit(1)

preload_fonts()

def level_text_metadata(region, level_value, font_size=None):
    text = f"LV{level_value}"
    if font_size is None:
        font_size = max(1, int(min(region.shape[:2]) * 0.4))
    
    badge_info = get_or_create_badge(font_size, level_value)
    badge_arr, left, top, right, bottom, font = badge_info
    text_w = right - left
    text_h = bottom - top

    x = CONFIG["level_left_px"] - left
    y = region.shape[0] - CONFIG["level_bottom_px"] - bottom
    return {
        "text": text,
        "font_size": font_size,
        "font": font,
        "text_w": text_w,
        "text_h": text_h,
        "x": x,
        "y": y,
        "visual_x": CONFIG["level_left_px"],
        "visual_y": region.shape[0] - CONFIG["level_bottom_px"] - text_h
    }

def draw_level_text(region, level_value, font_size=None):
    if font_size is None:
        font_size = max(1, int(min(region.shape[:2]) * 0.4))
    badge_info = get_or_create_badge(font_size, level_value)
    badge_arr, left, top, right, bottom, _ = badge_info
    text_w = right - left
    text_h = bottom - top
    out = region.copy()
    x = max(0, CONFIG["level_left_px"])
    y = max(0, region.shape[0] - CONFIG["level_bottom_px"] - text_h)
    alpha = badge_arr[:, :, 3:4].astype(np.float32) / 255.0
    color = cv2.cvtColor(badge_arr, cv2.COLOR_RGBA2BGR).astype(np.float32)
    base = out[y:y+text_h, x:x+text_w].astype(np.float32)
    out[y:y+text_h, x:x+text_w] = np.clip(color * alpha + base * (1.0 - alpha), 0, 255).astype(np.uint8)
    return out

def build_level_text_layer(region, level_value, font_size=None):
    if font_size is None:
        font_size = max(1, int(min(region.shape[:2]) * 0.4))
    badge_info = get_or_create_badge(font_size, level_value)
    badge_arr, left, top, right, bottom, _ = badge_info
    text_w = right - left
    text_h = bottom - top
    layer = np.zeros((region.shape[0], region.shape[1], 4), dtype=np.uint8)
    x = max(0, CONFIG["level_left_px"])
    y = max(0, region.shape[0] - CONFIG["level_bottom_px"] - text_h)
    layer[y:y+text_h, x:x+text_w] = cv2.cvtColor(badge_arr, cv2.COLOR_RGBA2BGRA)
    return layer

def apply_level_text_layer(region, level_layer):
    if level_layer is None:
        return region
    alpha = level_layer[:, :, 3:4].astype(np.float32) / 255.0
    text_bgr = level_layer[:, :, :3].astype(np.float32)
    base_bgr = region.astype(np.float32)
    blended = text_bgr * alpha + base_bgr * (1.0 - alpha)
    return np.clip(blended, 0, 255).astype(np.uint8)

class LevelDetector:
    def __init__(self, batch_size=OCR_BATCH_SIZE, workers=OCR_WORKERS):
        self.reader = get_easyocr_reader()
        self.batch_size = batch_size
        self.workers = workers

    @staticmethod
    def crop_level_area(image):
        height, width = image.shape[:2]
        crop_height = max(1, int(height * LEVEL_CROP_HEIGHT_RATIO))
        crop_width = max(1, int(width * LEVEL_CROP_WIDTH_RATIO))
        return image[0:crop_height, 0:crop_width]

    @staticmethod
    def crop_fast_level_area(image):
        height, width = image.shape[:2]
        x1 = max(0, min(width - 1, int(width * FAST_LEVEL_X_START_RATIO)))
        x2 = max(x1 + 1, min(width, int(width * FAST_LEVEL_X_END_RATIO)))
        y1 = max(0, min(height - 1, int(height * FAST_LEVEL_Y_START_RATIO)))
        y2 = max(y1 + 1, min(height, int(height * FAST_LEVEL_Y_END_RATIO)))
        return image[y1:y2, x1:x2]

    @staticmethod
    def level_text_boxes(image):
        height, width = image.shape[:2]
        boxes = []
        for x1_ratio, x2_ratio, y1_ratio, y2_ratio in (LEVEL_TITLE_BOX, LEVEL_PROGRESS_BOX):
            x1 = max(0, min(width - 1, int(width * x1_ratio)))
            x2 = max(x1 + 1, min(width, int(width * x2_ratio)))
            y1 = max(0, min(height - 1, int(height * y1_ratio)))
            y2 = max(y1 + 1, min(height, int(height * y2_ratio)))
            boxes.append([x1, x2, y1, y2])
        return boxes

    def detect_priority_gun_text(self, image):
        if not hasattr(self.reader, "recognize"):
            return ""
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            results = self.reader.recognize(
                gray,
                horizontal_list=[self.level_text_boxes(image)[0]],
                free_list=[],
                batch_size=self.batch_size,
                workers=self.workers,
            )
            return " ".join(result[1] for result in results)
        except Exception:
            return ""

    @staticmethod
    def extract_level(results):
        full_text = " ".join(result[1] for result in results)
        pipe_pattern = r"(?:\||I|l|V)\s*/\s*(\d+)"
        for _, text, _ in results:
            if re.search(pipe_pattern, text):
                return 1, full_text
        xy_pattern = r"(\d+)\s*/\s*(\d+)"
        for _, text, _ in results:
            match = re.search(xy_pattern, text)
            if match:
                x_value = int(match.group(1))
                y_value = int(match.group(2))
                if x_value == 3 and y_value == 3:
                    return x_value + 1, full_text
                return x_value, full_text
        match = re.search(r"(?:Cấp|Lv|Level)[.:\s]*(\d+)", full_text, re.IGNORECASE)
        if match:
            val = int(match.group(1))
            if 1 <= val <= 8:
                return val, full_text
        one_lookalikes = r"(?:Cấp|Lv|Level)[.:\s]*(?:\||I|l|i|\{|\}|\[|\]|!|/|\\)\b|(?:Cấp|Lv|Level)[.:\s]*[\{\|\[\]!ilI/]"
        if re.search(one_lookalikes, full_text, re.IGNORECASE):
            return 1, full_text
        if re.search(r"(?:Cấp|Lv|Level)[.:\s]*(?:G|b)\b", full_text, re.IGNORECASE):
            return 6, full_text
        if re.search(r"(?:Cấp|Lv|Level)[.:\s]*B\b", full_text, re.IGNORECASE):
            return 8, full_text
        return None, full_text

    def detect(self, image):
        return self.detect_many([self.crop_level_area(image)], [self.crop_fast_level_area(image)])[0]

    def detect_many(self, images, fast_images=None, candidate_names=None):
        if not images:
            return []
        if fast_images is None:
            fast_images = images
        fast_outputs = [None] * len(images)
        total = len(images)
        for index, image in enumerate(images):
            name_label = f" ({candidate_names[index]})" if candidate_names and index < len(candidate_names) else ""
            level_value, ocr_text = None, ""
            try:
                fast_results = self.reader.readtext(fast_images[index], canvas_size=256)
                level_value, ocr_text = self.extract_level(fast_results)
            except Exception:
                level_value, ocr_text = None, ""
            
            if level_value is None:
                try:
                    full_results = self.reader.readtext(image)
                    level_value, ocr_text = self.extract_level(full_results)
                except Exception:
                    level_value, ocr_text = None, ""
            
            fast_outputs[index] = (level_value, ocr_text)
            print(f"  [{index + 1:02d}/{total:02d}]{name_label} -> Level: {level_value if level_value else 'N/A'} | OCR: '{ocr_text}'", flush=True)
        return fast_outputs

    def detect_many_with_layout(self, images):
        if hasattr(self.reader, "readtext_batched"):
            all_results = [None] * len(images)
            groups = {}
            for index, image in enumerate(images):
                groups.setdefault(image.shape[:2], []).append((index, image))
            for group in groups.values():
                indexes = [index for index, _ in group]
                batch_images = [image for _, image in group]
                batch_results = self.reader.readtext_batched(batch_images, batch_size=self.batch_size, workers=self.workers)
                for index, results in zip(indexes, batch_results):
                    all_results[index] = results
        else:
            all_results = [self.reader.readtext(image, batch_size=self.batch_size, workers=self.workers) for image in images]
        return [self.extract_level(results) for results in all_results]

def detect_selected_item(image, hsv_lower=ORANGE_LOWER, hsv_upper=ORANGE_UPPER, morph_kernel_size=MORPH_KERNEL_SIZE, min_area=MIN_AREA, min_aspect=1.75, max_aspect=2.25):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lower = np.array(hsv_lower)
    upper = np.array(hsv_upper)
    mask = cv2.inRange(hsv, lower, upper)
    kernel = np.ones((morph_kernel_size, morph_kernel_size), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    img_h, img_w = image.shape[:2]
    candidates = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < min_area:
            continue
        aspect = w / h if h else 0
        if not (min_aspect <= aspect <= max_aspect):
            continue
        candidates.append((x, y, w, h, area, aspect))
        
    if not candidates:
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            if area < min_area:
                continue
            aspect = w / h if h else 0
            if 1.6 <= aspect <= 2.4:
                candidates.append((x, y, w, h, area, aspect))
                
    if not candidates:
        return None
        
    right_col = [c for c in candidates if c[0] >= img_w * 0.25]
    pool = right_col if right_col else candidates
    pool.sort(key=lambda c: (abs(c[5] - 2.0), -c[4]))
    best = pool[0]
    return (best[0], best[1], best[2], best[3])

def detect_gun_background_color(region):
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    pink_lower = np.array([140, 50, 50])
    pink_upper = np.array([170, 255, 255])
    pink_mask = cv2.inRange(hsv, pink_lower, pink_upper)
    pink_ratio = np.count_nonzero(pink_mask) / (region.shape[0] * region.shape[1])
    
    blue_lower = np.array([100, 50, 50])
    blue_upper = np.array([130, 255, 255])
    blue_mask = cv2.inRange(hsv, blue_lower, blue_upper)
    blue_ratio = np.count_nonzero(blue_mask) / (region.shape[0] * region.shape[1])
    
    if pink_ratio > blue_ratio and pink_ratio > 0.05:
        return "pink"
    elif blue_ratio > 0.05:
        return "blue"
    return None

def detect_and_crop_counter(img, card_rect=None):
    """
    Tự động nhận diện và cắt bộ đếm (elimination tracker) từ ảnh screenshot.
    Bỏ qua bộ đếm màu xám (chưa mở khóa / không trang bị).
    Chỉ cắt bộ đếm có màu sắc.
    """
    if img is None or img.size == 0:
        return None
    h, w = img.shape[:2]
    if card_rect is not None:
        card_gx = int(w * RIGHT_RATIO) + card_rect[0]
    else:
        card_gx = int(w * 0.78)
        
    roi_x2 = card_gx - 10
    roi_x1 = max(0, card_gx - int(w * 0.16))
    roi_y1 = int(h * 0.07)
    roi_y2 = int(h * 0.20)
    
    roi = img[roi_y1:roi_y2, roi_x1:roi_x2]
    if roi.size == 0:
        return None
        
    # 1. Kiểm tra mật độ cạnh (nền lab trống gần như không có cạnh)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 40, 120)
    edge_count = np.count_nonzero(edges)
    if edge_count < 300:
        return None
        
    # 2. Kiểm tra màu sắc: chỉ nhận bộ đếm có màu, bỏ qua bộ đếm màu xám (như ảnh 4)
    diff_rgb = np.max(roi, axis=2).astype(np.int32) - np.min(roi, axis=2).astype(np.int32)
    v = np.max(roi, axis=2)
    high_color = np.count_nonzero((diff_rgb > 35) & (v > 50))
    if high_color < 500:
        return None
        
    # 3. Tìm bounding box chính xác của bộ đếm trong ROI
    bg_sample = roi[2:8, 2:20]
    bg_color = np.median(bg_sample, axis=(0, 1))
    diff = np.linalg.norm(roi.astype(np.float32) - bg_color, axis=2)
    
    kernel = np.ones((5, 5), np.uint8)
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    badge_mask = (diff > 25) & (closed > 0)
    
    h_kernel = np.ones((3, 7), np.uint8)
    dilated = cv2.dilate(badge_mask.astype(np.uint8), h_kernel, iterations=1)
    
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
        
    best_bbox = None
    best_area = 0
    for c in contours:
        bx, by, bw, bh = cv2.boundingRect(c)
        if bw * bh > best_area and bw > 100 and bh > 30:
            best_area = bw * bh
            best_bbox = (bx, by, bw, bh)
            
    if not best_bbox:
        return None
        
    bx, by, bw, bh = best_bbox
    gx1 = roi_x1 + bx
    gy1 = roi_y1 + by
    gx2 = gx1 + bw
    gy2 = gy1 + bh
    
    badge_crop = img[gy1:gy2, gx1:gx2]
    if badge_crop is not None and badge_crop.size > 0:
        badge_crop = refine_counter_height(badge_crop)
    return badge_crop

def refine_counter_height(crop):
    """
    Giới hạn chiều cao bộ đếm bám sát tỷ lệ đa số (~4.3 - 4.8).
    Cắt bớt hiệu ứng kéo dài phía dưới (khói, băng tuyết, hào quang) nếu quá dài.
    """
    if crop is None or crop.size == 0:
        return crop
    h, w = crop.shape[:2]
    if w <= 0 or h <= 0:
        return crop
        
    aspect = w / h
    # Đa số các bộ đếm chuẩn có tỷ lệ w/h từ 4.0 đến 5.0 (trung bình ~4.5).
    # Chỉ cắt khi tỷ lệ bị dài quá mức (w/h < 3.8), ví dụ AKM Băng có khói dài (w/h ≈ 1.7).
    if aspect >= 3.8:
        return crop

    # Tìm vị trí đáy của khung số điện tử (d_bot) ở khoảng 65% bên phải
    right_part = crop[:, int(w * 0.35):]
    gray = cv2.cvtColor(right_part, cv2.COLOR_BGR2GRAY)
    digit_rows = np.where((gray > 160).any(axis=1))[0]
    
    cut_h = None
    if len(digit_rows) > 0:
        d_top = int(digit_rows[0])
        d_bot = int(digit_rows[-1])
        d_h = d_bot - d_top + 1
        
        if d_h >= 20 and d_bot >= 20:
            # Thông thường viền dưới khung số cách đáy số ~5-8px
            safe_bottom = d_bot + max(5, int(round(d_h * 0.08)))
            cut_h = safe_bottom
                
    # Nếu không tìm thấy số hoặc tỷ lệ sau khi cắt vẫn dài (> 1 / 3.8):
    # Ép bám sát tỷ lệ chuẩn của đa số bộ đếm (w / h ≈ 4.4 - 4.5)
    if cut_h is None or (w / cut_h < 3.8):
        cut_h = int(round(w / 4.4))
        
    # Giới hạn an toàn
    cut_h = max(20, min(h, cut_h))
    return crop[:cut_h, :]

def apply_counter_badge(region, counter_crop):
    """
    Ghép bộ đếm đã cắt vào góc dưới bên phải ô ảnh con (súng).
    Tỷ lệ kích thước cân đối (~47.5% chiều rộng thẻ súng, giữ nguyên tỷ lệ).
    """
    if counter_crop is None or counter_crop.size == 0 or region is None or region.size == 0:
        return region
    counter_crop = refine_counter_height(counter_crop)
    out = region.copy()
    card_h, card_w = out.shape[:2]
    bh, bw = counter_crop.shape[:2]
    
    target_bw = min(card_w, int(round(card_w * 0.475)))
    target_bh = min(card_h, max(1, int(round(bh * (target_bw / bw)))))
    
    badge_scaled = cv2.resize(counter_crop, (target_bw, target_bh), interpolation=cv2.INTER_AREA)
    bx = max(0, card_w - target_bw)
    by = max(0, card_h - target_bh)
    out[by:by + target_bh, bx:bx + target_bw] = badge_scaled
    return out

def white_block(width, height):
    return np.full((height, width, 3), 255, dtype=np.uint8)

def resize_optional_rgba(image, size):
    if image is None:
        return None
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA)

def normalize_processed_images_size(processed_images):
    if not processed_images:
        return 365, 177
    widths = [item.crop.shape[1] for item in processed_images if item.crop is not None and item.crop.size > 0]
    heights = [item.crop.shape[0] for item in processed_images if item.crop is not None and item.crop.size > 0]
    target_w = max(1, int(round(np.median(widths)))) if widths else 365
    target_h = max(1, int(round(np.median(heights)))) if heights else 177
    
    size = (target_w, target_h)
    for item in processed_images:
        if item.crop is not None and item.crop.size > 0:
            if item.crop.shape[1] != target_w or item.crop.shape[0] != target_h:
                item.crop = cv2.resize(item.crop, size, interpolation=cv2.INTER_AREA)
        if item.gun_crop is not None and item.gun_crop.size > 0:
            if item.gun_crop.shape[1] != target_w or item.gun_crop.shape[0] != target_h:
                item.gun_crop = cv2.resize(item.gun_crop, size, interpolation=cv2.INTER_AREA)
        if item.level_layer is not None and item.level_layer.size > 0:
            if item.level_layer.shape[1] != target_w or item.level_layer.shape[0] != target_h:
                item.level_layer = resize_optional_rgba(item.level_layer, size)
    return target_w, target_h


def build_grid_layout(processed_images, images_per_column=IMAGES_PER_COLUMN, row_resize_pct=ROW_RESIZE_PCT):
    if not processed_images:
        return None
    target_w, target_h = normalize_processed_images_size(processed_images)
    
    if images_per_column <= 0 or images_per_column >= len(processed_images):
        layout_items = []
        y_pos = 0
        for item in processed_images:
            layout_items.append(GridLayoutItem(processed=item, crop=item.crop, gun_crop=item.gun_crop, level_layer=item.level_layer, x=0, y=y_pos, width=target_w, height=target_h))
            y_pos += target_h
        return (target_w, y_pos, layout_items)
    
    columns = [processed_images[index:index + images_per_column] for index in range(0, len(processed_images), images_per_column)]
    layout_items = []
    x_pos = 0
    total_rows = images_per_column
    for column in columns:
        y_pos = 0
        for row_index in range(total_rows):
            if row_index < len(column):
                item = column[row_index]
                layout_items.append(GridLayoutItem(processed=item, crop=item.crop, gun_crop=item.gun_crop, level_layer=item.level_layer, x=x_pos, y=y_pos, width=target_w, height=target_h))
            else:
                block = white_block(target_w, target_h)
                dummy = ProcessedImage(index=0, file_name="", crop=block, gun_crop=block)
                layout_items.append(GridLayoutItem(processed=dummy, crop=block, gun_crop=block, level_layer=None, x=x_pos, y=y_pos, width=target_w, height=target_h))
            y_pos += target_h
        x_pos += target_w
    return (x_pos, total_rows * target_h, layout_items)

def render_layout_png(layout):
    width, height, layout_items = layout
    if width <= 0 or height <= 0:
        return None
    canvas = white_block(width, height)
    for item in layout_items:
        canvas[item.y:item.y + item.height, item.x:item.x + item.width] = item.crop
    return canvas

def concat_images_grid(processed_images, images_per_column=IMAGES_PER_COLUMN, row_resize_pct=ROW_RESIZE_PCT):
    layout = build_grid_layout(processed_images, images_per_column, row_resize_pct)
    if layout is None:
        return None
    return render_layout_png(layout)

def rgba_layer_from_bgr(image, alpha=255):
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    alpha_channel = np.full(image.shape[:2], alpha, dtype=np.uint8)
    return np.dstack((rgb, alpha_channel))

def rgb_channels_from_bgr(image):
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return np.stack((rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]))

def psd_image_layer(name, rgba_image, x, y, visible=True):
    layer = nested_layers.Image(name=name[:255], visible=visible, top=y, left=x, color_mode=enums.ColorMode.rgb)
    layer.set_channel(enums.ColorChannel.red, rgba_image[:, :, 0])
    layer.set_channel(enums.ColorChannel.green, rgba_image[:, :, 1])
    layer.set_channel(enums.ColorChannel.blue, rgba_image[:, :, 2])
    layer.set_channel(enums.ColorChannel.transparency, rgba_image[:, :, 3])
    return layer

def photoshop_js_string(value):
    return json.dumps(str(value), ensure_ascii=False)

def photoshop_path_string(path):
    return photoshop_js_string(str(path).replace("\\", "/"))

def photoshop_font_name():
    font_name = str(CONFIG.get("photoshop_font_ps_name", DEFAULT_CONFIG["photoshop_font_ps_name"]) or DEFAULT_CONFIG["photoshop_font_ps_name"]).strip()
    return font_name or DEFAULT_CONFIG["photoshop_font_ps_name"]

def rgba_alpha_bbox(image):
    if image is None or image.size == 0 or image.shape[2] < 4:
        return None
    ys, xs = np.nonzero(image[:, :, 3])
    if len(xs) == 0 or len(ys) == 0:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)

def layout_level_text_items(layout):
    _, _, layout_items = layout
    text_items = []
    for layer_index, item in enumerate(layout_items, start=1):
        if item.processed.level is None:
            continue
        metadata = level_text_metadata(item.crop, item.processed.level)
        bbox = rgba_alpha_bbox(item.level_layer)
        x = bbox[0] if bbox else metadata.get("visual_x", metadata["x"])
        y = bbox[1] if bbox else metadata.get("visual_y", metadata["y"])
        text_items.append({
            "name": f"text_level_{layer_index:03d}_LV{item.processed.level}",
            "text": metadata["text"],
            "x": item.x + x,
            "y": item.y + y + metadata["font_size"],
            "font_size": metadata["font_size"]
        })
    return text_items

def save_level_jsx(layout, psd_path, destination):
    font_name = photoshop_font_name()
    text_items = layout_level_text_items(layout)
    lines = [
        "#target photoshop",
        "app.displayDialogs = DialogModes.NO;",
        f"var psdFile = new File({photoshop_path_string(psd_path)});",
        "if (!psdFile.exists) { throw new Error('Không tìm thấy PSD: ' + psdFile.fsName); }",
        "var doc = app.open(psdFile);",
        "",
        "function hideRasterLevelLayers(container) {",
        "  for (var i = 0; i < container.layers.length; i++) {",
        "    var layer = container.layers[i];",
        "    if (layer.typename === 'LayerSet') {",
        "      hideRasterLevelLayers(layer);",
        "    } else if (/^level_\\d+_LV\\d+/.test(layer.name)) {",
        "      layer.visible = false;",
        "    }",
        "  }",
        "}",
        "",
        "hideRasterLevelLayers(doc);"
    ]
    for item in text_items:
        lines.extend([
            "",
            "var layer = doc.artLayers.add();",
            "layer.kind = LayerKind.TEXT;",
            f"layer.name = {photoshop_js_string(item['name'])};",
            "var textItem = layer.textItem;",
            f"textItem.contents = {photoshop_js_string(item['text'])};",
            f"textItem.font = {photoshop_js_string(font_name)};",
            f"textItem.size = UnitValue({item['font_size']}, 'px');",
            f"textItem.position = [UnitValue({item['x']}, 'px'), UnitValue({item['y']}, 'px')];",
            "var color = new SolidColor();",
            "color.rgb.red = 255;",
            "color.rgb.green = 255;",
            "color.rgb.blue = 255;",
            "textItem.color = color;"
        ])
    lines.extend(["", "doc.save();"])
    with destination.open("w", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")

def save_layout_psd(layout, destination):
    width, height, layout_items = layout
    background = np.full((height, width, 4), 255, dtype=np.uint8)
    gun_layers = []
    for layer_index, item in enumerate(layout_items, start=1):
        safe_name = Path(item.processed.file_name).stem[:80]
        gun_layers.append(psd_image_layer(f"gun_{layer_index:03d}_{safe_name}", rgba_layer_from_bgr(item.gun_crop), item.x, item.y))
    layers = gun_layers + [psd_image_layer("Background", background, 0, 0)]
    psd = nested_layers.nested_layers_to_psd(layers, enums.ColorMode.rgb, compression=enums.Compression.raw, size=(width, height))
    psd.image_data = image_data.ImageData(channels=rgb_channels_from_bgr(render_layout_png(layout)), compression=enums.Compression.raw)
    with destination.open("wb") as file:
        psd.write(file)

def list_images():
    image_files = []
    dirs_to_check = [INPUT_DIR]
    standalone_input = APP_DIR / "standalone" / "input"
    if standalone_input.is_dir():
        dirs_to_check.append(standalone_input)
    for directory in dirs_to_check:
        directory.mkdir(exist_ok=True)
        for path in directory.iterdir():
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            if FINAL_FILENAME_PATTERN.match(path.stem):
                continue
            image_files.append(path)
        if image_files:
            break
    return sorted(image_files, key=lambda item: item.name.casefold())

def random_output_dir():
    alphabet = string.ascii_uppercase + string.digits
    while True:
        name = "".join(random.choices(alphabet, k=10))
        path = APP_DIR / name
        if not path.exists():
            return path

def unique_destination(directory, file_name):
    destination = directory / file_name
    if not destination.exists():
        return destination
    stem = destination.stem
    suffix = destination.suffix
    counter = 1
    while True:
        candidate = directory / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1

def move_old_images(image_files):
    TRASH_DIR.mkdir(exist_ok=True)
    moved_count = 0
    for file_path in image_files:
        if not file_path.exists():
            continue
        destination = unique_destination(TRASH_DIR, file_path.name)
        shutil.move(str(file_path), str(destination))
        moved_count += 1
    return moved_count

def save_processed_crops(processed_images, output_dir):
    output_dir.mkdir(exist_ok=True)
    for image in processed_images:
        destination = unique_destination(output_dir, image.file_name)
        write_image(destination, image.crop)

def prepare_image(index, file_path):
    img = read_image(file_path)
    if img is None:
        return None
    height, width = img.shape[:2]
    right_portion = img[:, int(width * RIGHT_RATIO):]
    rect = detect_selected_item(right_portion, hsv_lower=ORANGE_LOWER, hsv_upper=ORANGE_UPPER, morph_kernel_size=MORPH_KERNEL_SIZE, min_area=MIN_AREA)
    if rect is None:
        return None
    x, y, w, h = rect
    region = right_portion[y:y + h, x:x + w]
    if CROP_INNER > 0:
        if region.shape[0] <= CROP_INNER * 2 or region.shape[1] <= CROP_INNER * 2:
            return None
        region = region[CROP_INNER:-CROP_INNER, CROP_INNER:-CROP_INNER]
    counter_crop = detect_and_crop_counter(img, rect)
    return ImageCandidate(index=index, file_name=file_path.name, crop=region, fast_level_area=LevelDetector.crop_fast_level_area(img), level_area=LevelDetector.crop_level_area(img), counter_crop=counter_crop)

def finalize_image(candidate, level_value, ocr_text):
    region = candidate.crop.copy()
    if candidate.counter_crop is not None:
        region = apply_counter_badge(region, candidate.counter_crop)
    gun_crop = region.copy()
    level_layer = None
    background_color = detect_gun_background_color(region)
    converted_3_3_level4 = is_converted_3_3_level4(level_value, ocr_text)
    if level_value:
        level_layer = build_level_text_layer(region, level_value)
        region = apply_level_text_layer(region, level_layer)
    return ProcessedImage(index=candidate.index, file_name=candidate.file_name, crop=region, gun_crop=gun_crop, level_layer=level_layer, level=level_value, ocr_text=ocr_text, background_color=background_color, converted_3_3_level4=converted_3_3_level4, counter_crop=candidate.counter_crop)

def special_gun_font_size(processed_images):
    font_sizes = [max(1, int(min(item.crop.shape[:2]) * 0.4)) for item in processed_images if item.crop is not None and item.crop.size > 0]
    if not font_sizes:
        return None
    return int(np.median(font_sizes))

def build_special_gun_image(special_type, index, reference_images, insert_position):
    config = SPECIAL_GUNS.get(special_type)
    if not config:
        return None
    asset_path = config["asset"]
    image = read_image(asset_path)
    if image is None:
        print(f"Không tải được ảnh {config['label']}: {asset_path}")
        return None
    if CROP_INNER > 0:
        if image.shape[0] <= CROP_INNER * 2 or image.shape[1] <= CROP_INNER * 2:
            print(f"Ảnh {config['label']} quá nhỏ để cắt viền.")
            return None
        image = image[CROP_INNER:-CROP_INNER, CROP_INNER:-CROP_INNER]
    
    target_w = int(round(np.median([r.crop.shape[1] for r in reference_images]))) if reference_images else image.shape[1]
    target_h = int(round(np.median([r.crop.shape[0] for r in reference_images]))) if reference_images else image.shape[0]
    image = cv2.resize(image, (target_w, target_h), interpolation=cv2.INTER_AREA)
    gun_crop = image.copy()
    
    level_layer = build_level_text_layer(image, 7, special_gun_font_size(reference_images))
    image = apply_level_text_layer(image, level_layer)
    return ProcessedImage(index=index, file_name=asset_path.name, crop=image, gun_crop=gun_crop, level_layer=level_layer, level=7, ocr_text="", background_color=None, converted_3_3_level4=False, special_type=special_type, special_insert_position=insert_position)

def build_special_gun_images(selected_types, reference_images, positions):
    special_images = []
    start_index = max((item.index for item in reference_images), default=0) + 1
    if not positions:
        positions = {}
    for offset, special_type in enumerate(selected_types):
        item = build_special_gun_image(special_type, start_index + offset, reference_images, positions.get(special_type))
        if item is not None:
            special_images.append(item)
    return special_images

def insert_special_gun_images(processed_images, special_images):
    combined = list(processed_images)
    for item in special_images:
        position = item.special_insert_position
        if position is None:
            combined.append(item)
            continue
        insert_index = max(0, min(position - 1, len(combined)))
        if insert_index < len(combined) and combined[insert_index].special_insert_position == position:
            insert_index += 1
        combined.insert(insert_index, item)
    return combined

def detect_weapon_family(text: str) -> tuple[int, str]:
    normalized = re.sub(r"[^A-Z0-9]", "", str(text).upper())
    # Thứ tự ưu tiên người dùng yêu cầu: M416 -> AUG -> UMP -> AKM
    if re.search(r"M4(?:16|I6|1G|IG|1B|IB|6)?", normalized) or "M416" in normalized:
        return 0, "M416"
    if re.search(r"A(?:U|V)(?:G|6)", normalized) or "AUG" in normalized:
        return 1, "AUG"
    if re.search(r"(?:U|V|J|IJ)?(?:MP|NP)(?:45)?", normalized) or "UMP" in normalized:
        return 2, "UMP"
    if re.search(r"AK(?:M|N|47)?", normalized) or "AKM" in normalized:
        return 3, "AKM"

    other_patterns = (
        ("AWM", r"A(?:W|VV)M"),
        ("GROZA", r"GROZA|GR0ZA"),
        ("KAR98", r"KAR(?:98|9B|9G)|K98"),
        ("M24", r"M24(?![0-9])"),
        ("M249", r"M249"),
        ("SCARL", r"SCAR"),
        ("VECTOR", r"VECTOR"),
        ("DP28", r"DP(?:28|2B)"),
        ("THOMPSON", r"THOMP|TOMMY"),
        ("BERYL", r"M762|BERYL"),
        ("QBZ", r"QBZ"),
        ("SKS", r"SKS"),
        ("MINI14", r"MINI"),
        ("SLR", r"SLR"),
        ("MK14", r"MK14"),
        ("MK47", r"MK47"),
        ("PAN", r"PAN|CHAO"),
        ("DBS", r"DBS"),
    )
    for name, pat in other_patterns:
        if re.search(pat, normalized):
            return 4, name

    letters = re.sub(r"[^A-Z]", "", normalized)
    return 5, letters[:6] if letters else normalized[:6]

def gun_priority_rank(text):
    return detect_weapon_family(text)[0]

def sort_processed_images(processed_images):
    def sort_key(item: ProcessedImage):
        # 1. Level từ cao xuống thấp (LV8 -> LV7 -> LV6 -> LV5 -> ...)
        level = item.level if item.level is not None else 0
        
        # 2. Cùng level: có bộ đếm ưu tiên lên đầu
        has_counter = 0 if getattr(item, "counter_crop", None) is not None else 1
        
        # 3 & 4. Loại súng ưu tiên (M416 -> AUG -> UMP -> AKM -> khác)
        # và gom các skin cùng 1 loại súng lại gần nhau
        prio_rank, weapon_name = detect_weapon_family(item.ocr_text)
        
        is_demoted_special = getattr(item, "special_type", None) in SPECIAL_GUNS
        special_level_rank = 1 if level == 7 and is_demoted_special else 0
        converted_3_3_level4_rank = 1 if level == 4 and getattr(item, "converted_3_3_level4", False) else 0
        background_rank = 1 if getattr(item, "background_color", None) == "blue" else 0
        
        return (
            -level,
            has_counter,
            prio_rank,
            weapon_name,
            special_level_rank,
            converted_3_3_level4_rank,
            background_rank,
            item.index
        )
    return sorted(processed_images, key=sort_key)

def is_converted_3_3_level4(level_value, text):
    if level_value != 4:
        return False
    return bool(re.search(r"(?<!\d)3\s*/\s*3(?!\d)", str(text)))

def parse_args():
    parser = argparse.ArgumentParser(description="Cắt selected item, nhận diện level và ghép ảnh.", add_help=False)
    parser.add_argument("-i", dest="images_per_column", type=non_negative_int, default=IMAGES_PER_COLUMN, metavar="N", help="Số ảnh trên mỗi cột; 0 là ghép 1 cột")
    parser.add_argument("-s", dest="sort_guns", action="store_true", default=SORT_GUNS, help="Sắp xếp lv8 trước lv7; cùng level ưu tiên M416, AKM, UMP, AUG, sau đó nền hồng")
    args = parser.parse_args()
    args.special_guns = []
    return args

def prompt_special_guns():
    print()
    add_special = input("Bạn có muốn thêm AKM Hoả Ngục, UMP Sinh Nhật Không? Y/N: ").strip()
    if add_special.casefold() != "y":
        return []
    print()
    print("Thêm cái nào?")
    print("1. AKM Hoả Ngục")
    print("2. UMP Sinh Nhật")
    print("3. Cả 2")
    choice = input("Chọn 1/2/3: ").strip()
    selected = SPECIAL_GUN_CHOICES.get(choice)
    if not selected:
        print("Lựa chọn không hợp lệ.")
        sys.exit(1)
    return selected

def prompt_special_gun_position(label, max_position):
    while True:
        value = input(f"Nhập vị trí cho {label} (1-{max_position}): ").strip()
        try:
            position = int(value)
            if 1 <= position <= max_position:
                return position
            print(f"Vị trí không hợp lệ. Vui lòng nhập số từ 1 đến {max_position}.")
        except ValueError:
            position = 0
            print(f"Vị trí không hợp lệ. Vui lòng nhập số từ 1 đến {max_position}.")

def prompt_special_gun_positions(selected_types, base_count):
    positions = {}
    current_count = base_count
    for special_type in selected_types:
        label = SPECIAL_GUNS[special_type]["label"]
        max_position = current_count + 1
        positions[special_type] = prompt_special_gun_position(label, max_position)
        current_count += 1
    return positions

def prompt_run_options(args):
    if len(sys.argv) > 1:
        return args
    print()
    images_per_column = input("Nhập số ảnh trên 1 cột (bỏ trống để ghép 1 cột): ").strip()
    if images_per_column:
        try:
            args.images_per_column = non_negative_int(images_per_column)
        except argparse.ArgumentTypeError as exc:
            print(exc)
            sys.exit(1)
    args.sort_guns = True
    args.special_guns = []
    return args

def main():
    log_file = Path(r"d:\Ghep-Anh\Auto-Cut\DienLV\main_exec.log")
    with log_file.open("w", encoding="utf-8") as _flog:
        def mlog(msg):
            print(msg, flush=True)
            _flog.write(str(msg) + "\n")
            _flog.flush()

        mlog("=== KHỞI ĐỘNG MAIN ===")
        args = parse_args()
        run_first_time_setup_if_needed()
        require_valid_license()
        args = prompt_run_options(args)
        if not 0 < RIGHT_RATIO < 1:
            sys.exit(1)
        if CROP_INNER < 0:
            sys.exit(1)
        if WORKERS < 1:
            sys.exit(1)
        if OCR_BATCH_SIZE < 1:
            sys.exit(1)
        if OCR_WORKERS < 0:
            sys.exit(1)
        if ROW_RESIZE_PCT < 0:
            sys.exit(1)
        
        image_files = list_images()
        if not image_files:
            mlog("[!] Không tìm thấy ảnh nào trong thư mục input.")
            wait_before_exit()
            sys.exit(1)
            
        mlog(f"\n[*] Tìm thấy {len(image_files)} ảnh cần xử lý.")
        mlog("[*] Đang nhận diện và cắt khung súng...")
        candidates = []
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = [executor.submit(prepare_image, index, file_path) for index, file_path in enumerate(image_files, start=1)]
            for future in as_completed(futures):
                candidate = future.result()
                if candidate is not None:
                    candidates.append(candidate)
                    
        if not candidates:
            mlog("[!] Không nhận diện được khung súng nào hợp lệ từ ảnh đầu vào.")
            wait_before_exit()
            sys.exit(1)
            
        candidates.sort(key=lambda item: item.index)
        mlog(f"[*] Nhận diện được {len(candidates)}/{len(image_files)} khung súng.")
        mlog(f"[*] Đang nhận diện Level súng bằng OCR...")
        detector = LevelDetector(batch_size=OCR_BATCH_SIZE, workers=OCR_WORKERS)
        
        level_areas = [c.level_area for c in candidates]
        fast_level_areas = [c.fast_level_area for c in candidates]
        candidate_names = [c.file_name for c in candidates]
        ocr_outputs = detector.detect_many(level_areas, fast_level_areas, candidate_names=candidate_names)
        
        mlog("\n[*] Đang vẽ chữ Level lên từng ảnh súng...")
        processed_images = []
        for candidate, (level_value, ocr_text) in zip(candidates, ocr_outputs):
            processed = finalize_image(candidate, level_value, ocr_text)
            processed_images.append(processed)
            counter_tag = " [+Bộ Đếm]" if processed.counter_crop is not None else ""
            mlog(f"  [+] {candidate.file_name} -> LV{level_value or '?'}{counter_tag}")
            
        if not processed_images:
            mlog("[!] Không có ảnh súng nào được xử lý.")
            wait_before_exit()
            sys.exit(1)
            
        special_positions = {}
        if args.special_guns and not args.sort_guns:
            print()
            special_positions = prompt_special_gun_positions(args.special_guns, len(processed_images))
                
        special_images = build_special_gun_images(args.special_guns, processed_images, special_positions)
        if args.sort_guns:
            processed_images.extend(special_images)
            processed_images = sort_processed_images(processed_images)
        elif special_images:
            processed_images = insert_special_gun_images(processed_images, special_images)
            
        mlog("[*] Đang ghép bố cục...")
        layout = build_grid_layout(processed_images, args.images_per_column, ROW_RESIZE_PCT)
        if layout is None:
            mlog("[!] Không thể tạo bố cục ảnh.")
            wait_before_exit()
            sys.exit(1)
            
        final_image = render_layout_png(layout)
        if final_image is None:
            mlog("[!] Không thể render ảnh ghép.")
            wait_before_exit()
            sys.exit(1)
            
        output_dir = random_output_dir()
        output_dir.mkdir(exist_ok=True)
        final_path = output_dir / f"{output_dir.name}.png"
        psd_path = output_dir / f"{output_dir.name}.psd"
        jsx_path = output_dir / f"{output_dir.name}.jsx"
        
        mlog(f"[*] Đang xuất kết quả vào: {output_dir.name}...")
        save_processed_crops(processed_images, output_dir / "anhle")
        has_counter = any(p.counter_crop is not None for p in processed_images)
        if has_counter:
            bodem_dir = output_dir / "bodem"
            bodem_dir.mkdir(exist_ok=True)
            for p in processed_images:
                if p.counter_crop is not None:
                    dest = unique_destination(bodem_dir, p.file_name)
                    write_image(dest, p.counter_crop)
        write_image(final_path, final_image)
        save_layout_psd(layout, psd_path)
        save_level_jsx(layout, psd_path, jsx_path)
        move_old_images(image_files)

        counter_count = sum(1 for p in processed_images if p.counter_crop is not None)
        mlog("\n" + "=" * 64)
        mlog("                     XỬ LÝ HOÀN TẤT THÀNH CÔNG!")
        mlog("=" * 64)
        mlog(f" Mã súng / Thư mục: {output_dir.name}")
        mlog(f" Đường dẫn        : {output_dir}")
        mlog(f" Ảnh ghép         : {final_path.name}")
        mlog(f" Thư mục ảnh lẻ   : anhle/ ({len(processed_images)} ảnh)")
        if counter_count > 0:
            mlog(f" Thư mục bộ đếm   : bodem/ ({counter_count} ảnh)")
        mlog(f" File PSD         : {psd_path.name}")
        mlog(f" File JSX         : {jsx_path.name}")
        mlog("=" * 64)
        wait_before_exit()

if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        if exc.code not in (0, None):
            wait_before_exit()
        raise
    except Exception as exc:
        print()
        print(f"Lỗi: {exc}")
        wait_before_exit()
        sys.exit(1)
