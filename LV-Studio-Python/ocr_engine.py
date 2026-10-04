"""EasyOCR vi/en, research-first recognition matching the supplied DienLV workflow."""
import re
import os
import logging
import gc
import time
import threading
import unicodedata
from pathlib import Path
from title_regions import title_region, research_probe_box


def normalized(text):
    text = unicodedata.normalize('NFKC', str(text)).replace('⁄', '/').replace('∕', '/')
    return ''.join(c for c in unicodedata.normalize('NFD', text) if not unicodedata.combining(c))


def progress_level(text):
    match = re.search(r'(?<![\dA-Za-z])(\d{1,2}|[Il|V])\s*/\s*(\d{1,2})(?!\d)', normalized(text))
    if not match:
        return None
    current = 1 if match[1] in ('I', 'l', '|', 'V') else int(match[1])
    maximum = int(match[2])
    if not 1 <= current <= maximum <= 20:
        return None
    return {'lv': 4 if (current, maximum) == (3, 3) else current,
            'current': current, 'maximum': maximum, 'source': 'research'}


def roman_level(token):
    token = token.upper().replace('|', 'I').replace('L', 'I')
    values = {'I': 1, 'V': 5, 'X': 10}
    if not token or any(c not in values for c in token):
        return None
    value = sum(-values[c] if i + 1 < len(token) and values[c] < values[token[i + 1]] else values[c]
                for i, c in enumerate(token))
    valid = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
             'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI', 'XVII', 'XVIII', 'XIX', 'XX']
    return value if 1 <= value <= 20 and valid[value] == token else None


def title_level(text):
    text = normalized(text).strip()
    match = re.search(r'\b(?:Cap|LV|Level)\s*[:.\-]?\s*(\d{1,2})(?!\d)', text, re.I)
    if match:
        value = int(match[1])
        return value if 1 <= value <= 20 else None
    match = re.search(r'\b(?:Cap|LV|Level)\s*([GIl|])\s*[).,;]*\s*$', text, re.I)
    if match:
        return 6 if match[1].upper() == 'G' else 1
    match = re.search(r'(?:^|[\s(\[\-:])([IVXil|]{1,8})\s*[)\].,;]*\s*$', text, re.I)
    return roman_level(match[1]) if match else None


WEAPONS = [('M416', r'M[4A][1IL|][6GE]'), ('AUG', r'AUG'), ('UMP', r'UMP(?:45|9)?'),
           ('AKM', r'AKM'), ('SCAR-L', r'SCAR-?L'), ('M762', r'M762'), ('M16A4', r'M16A4'),
           ('ACE32', r'ACE32'), ('G36C', r'G36C'), ('QBZ', r'QBZ'), ('FAMAS', r'FAMAS'),
           ('GROZA', r'GROZA'), ('P90', r'P90'), ('VECTOR', r'VECTOR'), ('UZI', r'UZI'),
           ('PP19', r'PP-?19|BIZON'), ('MP5K', r'MP5K'), ('TOMMY GUN', r'TOMMY|THOMPSON'),
           ('M249', r'M249'), ('DP28', r'DP-?28'), ('MG3', r'MG3'), ('AWM', r'AWM'),
           ('AMR', r'AMR'), ('M24', r'M24'), ('KAR98K', r'KAR98K'), ('MINI14', r'MINI14'),
           ('SKS', r'SKS'), ('SLR', r'SLR'), ('MK14', r'MK14'), ('MK12', r'MK12'),
           ('VSS', r'VSS'), ('QBU', r'QBU'), ('DBS', r'DBS'), ('S12K', r'S12K'),
           ('S686', r'S686'), ('S1897', r'S1897'), ('NS2000', r'NS2000'), ('M1014', r'M1014')]


PRIORITY_WEAPONS = {'M416', 'AUG', 'UMP', 'AKM'}


def known_weapon_name(text):
    original = normalized(text).upper()
    text = re.sub(r'\s+', '', original)
    found = next((name for name, pattern in WEAPONS if re.search(pattern, text)), 'OTHER')
    if found != 'OTHER': return found
    for name, alias in [('AUG', r'AU[6C]'), ('AKM', r'AKIVI')]:
        if re.search(r'(?<![A-Z0-9])' + alias + r'(?![A-Z0-9])', original): return name
    return 'OTHER'


def weapon_name(text):
    name = known_weapon_name(text)
    return name if name in PRIORITY_WEAPONS else 'OTHER'


def extract(results, allow_title=False):
    texts = [str(item[1]) for item in results]
    full_text = ' '.join(texts)
    for text in texts + [full_text]:
        value = progress_level(text)
        if value:
            return value, full_text
    if allow_title:
        for text in texts + [full_text]:
            value = title_level(text)
            if value:
                return {'lv': value, 'current': value, 'source': 'title'}, full_text
    return None, full_text


def uid_from_results(results):
    # Require UID label: unrelated rank, levels, and item counts are not IDs.
    for item in results:
        text = str(item[1])
        match = re.search(r'U[I1l|]D\s*[:：]?\s*([0-9OoIl| ]{8,20})', text, re.I)
        if match:
            value = match[1].translate(str.maketrans({'O':'0','o':'0','I':'1','l':'1','|':'1'})).replace(' ', '')
            if re.fullmatch(r'\d{8,14}', value):
                return value, float(item[2])
    # Some OCR runs split the label and number into adjacent boxes.
    for item in results:
        if not re.fullmatch(r'U[I1l|]D\s*[:：]?', str(item[1]).strip(), re.I):
            continue
        box = item[0]; right = max(p[0] for p in box); cy = sum(p[1] for p in box)/4
        height = max(p[1] for p in box)-min(p[1] for p in box)
        for other in results:
            text = str(other[1]).replace(' ', '')
            if not re.fullmatch(r'\d{8,14}', text): continue
            points = other[0]; left = min(p[0] for p in points); oy = sum(p[1] for p in points)/4
            if 0 <= left-right <= max(25,height*4) and abs(oy-cy) <= max(5,height*.7):
                return text, min(float(item[2]),float(other[2]))
    return None, 0.0


class LevelEngine:
    def __init__(self, model_dir, device=None):
        self.model_dir = Path(model_dir)
        self.lock = threading.RLock()
        self.reader = None
        self.state = 'Đang chuẩn bị EasyOCR…'
        self.error = None
        self.device_preference = device or os.environ.get('LV_STUDIO_DEVICE', 'auto')
        self.device = 'cpu'
        self.device_name = 'CPU'
        self.device_note = ''

    def _reader(self, gpu, download=False):
        import easyocr
        return easyocr.Reader(['vi', 'en'], gpu=gpu, verbose=False,
                              model_storage_directory=str(self.model_dir),
                              download_enabled=download)

    def _use_cpu(self, reason='', download=False):
        self.reader = None
        self.device = 'cpu'
        self.device_name = 'CPU'
        self.device_note = reason
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
        self.reader = self._reader(False, download)
        self.state = 'EasyOCR đã sẵn sàng · CPU' + (' · ' + reason if reason else '')

    def _readtext(self, pixels, **kwargs):
        try:
            return self.reader.readtext(pixels, **kwargs)
        except Exception:
            if self.device != 'cuda':
                raise
            logging.exception('GPU OCR failed; retrying this region on CPU')
        # Leave the exception context before releasing the GPU models.
        self._use_cpu('GPU gặp lỗi; đã tự chuyển CPU')
        return self.reader.readtext(pixels, **kwargs)

    def _read_line(self, pixels):
        import cv2
        gray = cv2.cvtColor(pixels, cv2.COLOR_BGR2GRAY)
        try:
            return self.reader.recognize(gray, workers=0)
        except Exception:
            if self.device != 'cuda':
                raise
            logging.exception('GPU title recognition failed; retrying on CPU')
        self._use_cpu('GPU gặp lỗi; đã tự chuyển CPU')
        return self.reader.recognize(gray, workers=0)

    def _adaptive_title(self, pixels, initial_text, trace, logical_size=None):
        """Only bypass broad detection when progress is absent and title agrees."""
        region = title_region(pixels, logical_size)
        if region is None:
            return None
        pixel_h, pixel_w = pixels.shape[:2]
        w, h = logical_size or (pixel_w, pixel_h)
        x0, y0, x1, y1 = research_probe_box(w, h, region['profile'])
        x1, y1 = min(pixel_w, x1), min(pixel_h, y1)
        probe = self._readtext(pixels[y0:y1, x0:x1], canvas_size=640, workers=0)
        progress, probe_text = extract(probe)
        trace.append({'region': 'research-layout-probe', 'profile': region['profile'],
                      'box': [x0, y0, x1, y1], 'text': probe_text})
        if progress:
            confidence = self._confidence(probe, progress)
            if confidence >= 70:
                return progress, probe_text, confidence
            return None
        # A visible research label or incomplete fraction may still contain the
        # real current level. Do not replace it with an early title guess.
        hints = normalized(initial_text + ' ' + probe_text).lower()
        if '/' in hints or 'nghien' in hints or 'tien' in hints:
            return None
        x0, y0, x1, y1 = region['box']
        crop = pixels[y0:y1, x0:x1]
        full = self._read_line(crop)
        full_text = ' '.join(str(item[1]) for item in full)
        full_lv = title_level(full_text)
        full_conf = min((float(item[2]) for item in full), default=0)
        # No level marker: this may be a partial title; preserve the broad path.
        if full_lv is None or full_conf < .45:
            trace.append({'region': 'title-located', **region, 'text': full_text, 'name_confidence': full_conf, 'accepted': False})
            return None
        suffix = self._read_line(crop[:, int(crop.shape[1]*.60):])
        suffix_text = ' '.join(str(item[1]) for item in suffix)
        suffix_lv = title_level(suffix_text)
        suffix_conf = min((float(item[2]) for item in suffix), default=0)
        # Check with a second crop; a confidence score alone is not sufficient.
        accepted = full_lv == suffix_lv and suffix_conf >= .55
        trace.append({'region': 'title-located', **region, 'text': full_text,
                      'confirmation': suffix_text, 'name_confidence': full_conf, 'accepted': accepted})
        if not accepted:
            return None
        result = {'lv': full_lv, 'current': full_lv, 'source': 'title'}
        return result, full_text, round(100 * min(full_conf, suffix_conf), 1)

    def warm(self, download=False):
        with self.lock:
            if self.reader is not None:
                return
            if self.error is not None:
                raise RuntimeError(self.error)
            try:
                import torch
                import easyocr
                torch.set_num_threads(4)
                self.model_dir.mkdir(parents=True, exist_ok=True)
                gpu_ok = False
                if self.device_preference != 'cpu':
                    try:
                        gpu_ok = torch.cuda.is_available()
                    except Exception:
                        logging.exception('CUDA detection failed')
                if gpu_ok:
                    try:
                        self.state = 'Đang nạp EasyOCR trên GPU…'
                        # A real operation catches unsupported architectures/drivers.
                        probe = torch.ones((8, 8), device='cuda')
                        (probe @ probe).sum().item()
                        del probe
                        name = torch.cuda.get_device_name(0)
                        reader = self._reader('cuda', download)
                        self.device = 'cuda'
                        self.device_name = name
                        self.reader = reader
                        self.state = 'EasyOCR đã sẵn sàng · GPU: ' + name
                    except Exception:
                        logging.exception('GPU initialization failed; using CPU')
                    if self.reader is None:
                        self._use_cpu('GPU không dùng được; đã tự chuyển CPU', download)
                else:
                    self._use_cpu('CUDA không khả dụng' if self.device_preference != 'cpu'
                                  else 'Chế độ CPU', download)
                self.error = None
            except Exception as exc:
                self.error = str(exc)
                self.state = 'Chưa khởi động được EasyOCR'
                raise

    def recognize_uid(self, image, cropped=False):
        import numpy as np
        with self.lock:
            self.warm(download=False)
            image = image.convert('RGB')
            image.thumbnail((2400, 2400))
            w, h = image.size
            # Profile UID in the upper portion of the blue data panel.
            region = image if cropped else image.crop((int(w*.36), int(h*.10), int(w*.72), int(h*.29)))
            if cropped and region.width < 600:
                factor = min(600/region.width, 800/region.height)
                if factor > 1: region = region.resize((round(region.width*factor),round(region.height*factor)))
            pixels = np.asarray(region)[:, :, ::-1].copy()
            readings = self._readtext(pixels, canvas_size=1280, mag_ratio=2,
                                      allowlist='UIDuid:：0123456789OlI| ', workers=0)
            value, confidence = uid_from_results(readings)
            if value is None and cropped:
                candidates = [(re.sub(r'\s+', '', str(item[1])), float(item[2])) for item in readings]
                numeric = [(text,score) for text,score in candidates if re.fullmatch(r'\d{8,14}',text)]
                if len(numeric) == 1: value,confidence = numeric[0]
            return {'uid': value, 'confidence': round(confidence*100, 2)}

    def recognize(self, image, logical_size=None):
        import numpy as np
        with self.lock:
            self.warm(download=False)
            # EasyOCR accepts the BGR array used by the original Python tool.
            preparing = time.perf_counter()
            pixels = np.asarray(image.convert('RGB'))[:, :, ::-1].copy()
            pixel_height, pixel_width = pixels.shape[:2]
            width, height = logical_size or (pixel_width, pixel_height)
            fast_y0 = min(pixel_height - 1, int(height * .08))
            fast_y1 = min(pixel_height, max(fast_y0 + 1, int(height * .20)))
            fast = pixels[fast_y0:fast_y1, :min(pixel_width, max(1, int(width * .25)))]
            top = pixels[:min(pixel_height, max(1, int(height * .18))),
                         :min(pixel_width, max(1, int(width * .60)))]
            prepare_ms = (time.perf_counter() - preparing) * 1000
            level_started = time.perf_counter()
            trace = []
            result = None
            text = ''
            confidence = 0
            try:
                readings = self._readtext(fast, canvas_size=256, workers=0)
                result, text = extract(readings)
                if result:
                    confidence = self._confidence(readings, result)
                trace.append({'region': 'research', 'text': text})
            except Exception as exc:
                trace.append({'region': 'research', 'error': str(exc)})
            if result is None:
                try:
                    adaptive = self._adaptive_title(pixels, text, trace, logical_size)
                    if adaptive is not None:
                        result, text, confidence = adaptive
                except Exception as exc:
                    trace.append({'region': 'title-located', 'error': str(exc)})
            if result is None:
                try:
                    readings = self._readtext(top, workers=0)
                    result, text = extract(readings, allow_title=True)
                    if result:
                        confidence = self._confidence(readings, result)
                    trace.append({'region': 'top-fallback', 'text': text})
                except Exception as exc:
                    trace.append({'region': 'top-fallback', 'error': str(exc)})
            level_ms = (time.perf_counter() - level_started) * 1000
            name_started = time.perf_counter()
            detected = known_weapon_name(text)
            weapon = detected if detected in PRIORITY_WEAPONS else 'OTHER'
            # Reuse known non-priority names from LV OCR to avoid an extra pass.
            # Otherwise one title pass checks for the four priority weapons.
            if detected == 'OTHER':
                # With a located text line, recognition can skip text detection.
                # Reuse an earlier direct title reading if LV fallback already did it.
                try:
                    previous = next((item for item in reversed(trace)
                                     if item['region'] == 'title-located' and 'name_confidence' in item), None)
                    if previous is not None:
                        direct_text, direct_conf = previous['text'], previous['name_confidence']
                    else:
                        region = title_region(pixels, logical_size)
                        direct_text, direct_conf = '', 0
                        if region:
                            x0, y0, x1, y1 = region['box']
                            direct = self._read_line(pixels[y0:y1, x0:x1])
                            direct_text = ' '.join(str(item[1]) for item in direct)
                            direct_conf = min((float(item[2]) for item in direct), default=0)
                    direct_name = known_weapon_name(direct_text)
                    if direct_name != 'OTHER' and direct_conf >= .45:
                        detected = direct_name
                        weapon = direct_name if direct_name in PRIORITY_WEAPONS else 'OTHER'
                    trace.append({'region': 'name-located', 'text': direct_text,
                                  'accepted': detected != 'OTHER'})
                except Exception as exc:
                    trace.append({'region': 'name-located', 'error': str(exc)})
            if detected == 'OTHER':
                try:
                    title_height = min(height, int(max(height * .078, width * .058)))
                    title = pixels[:min(pixel_height, title_height), :min(pixel_width, int(width * .78))]
                    words = self._readtext(title, canvas_size=640, workers=0)
                    fallback_text = ' '.join(str(item[1]) for item in words)
                    detected = known_weapon_name(fallback_text)
                    weapon = detected if detected in PRIORITY_WEAPONS else 'OTHER'
                    trace.append({'region': 'name-top', 'text': fallback_text, 'accepted': detected != 'OTHER'})
                except Exception:
                    pass  # A missing name never discards an already recognized level.
            if detected == 'OTHER':
                try:
                    # Rescue wrapped titles and faint lettering only after fast paths fail.
                    from PIL import Image, ImageEnhance, ImageOps
                    stop_y = min(pixel_height, max(1, int(height*.18)))
                    stop_x = min(pixel_width, max(1, int(width*.80)))
                    region_image = Image.fromarray(pixels[:stop_y, :stop_x, ::-1]).convert('L')
                    region_image = ImageEnhance.Contrast(ImageOps.autocontrast(region_image)).enhance(1.4)
                    rescue = self._readtext(np.asarray(region_image), canvas_size=1600, mag_ratio=2, workers=0)
                    candidates = [(known_weapon_name(str(item[1])), float(item[2])) for item in rescue]
                    accepted = next((name for name, score in candidates if name != 'OTHER' and score >= .45), None)
                    if accepted:
                        detected = accepted
                        weapon = accepted if accepted in PRIORITY_WEAPONS else 'OTHER'
                    trace.append({'region': 'name-rescue', 'text': ' '.join(str(item[1]) for item in rescue),
                                  'accepted': accepted is not None})
                except Exception as exc:
                    trace.append({'region': 'name-rescue', 'error': str(exc)})
            output = {**(result or {'lv': None}), 'weapon': weapon, 'confidence': confidence,
                      'name_known': detected != 'OTHER', 'engine': 'EasyOCR vi/en', 'device': self.device, 'device_name': self.device_name, 'trace': trace,
                      'timings': {'prepare_ms': round(prepare_ms, 2), 'lv_ms': round(level_ms, 2),
                                  'name_ms': round((time.perf_counter() - name_started) * 1000, 2)}}
            if result is None:
                output['reviewReason'] = 'EasyOCR chưa đọc được cấp độ; hãy mở ảnh gốc để kiểm tra và điền LV.'
            return output

    @staticmethod
    def _confidence(readings, result):
        matches = [float(item[2]) for item in readings
                   if (progress_level(item[1]) or {}).get('lv') == result['lv']
                   or (result['source'] == 'title' and title_level(item[1]) == result['lv'])]
        if not matches:
            matches = [float(item[2]) for item in readings]
        return round(100 * min(matches), 1) if matches else 0
