"""Locate visible title text in tablet and wide phone screenshot layouts.

Dimensions choose the search envelope; pixel evidence chooses the actual box.
Unknown or ambiguous layouts return None to preserve the legacy OCR path.
"""


def title_region(pixels, logical_size=None):
    import numpy as np

    pixel_height, pixel_width = pixels.shape[:2]
    width, height = logical_size or (pixel_width, pixel_height)
    aspect = width / height
    if not 1.15 <= aspect <= 2.7 or width < 400 or height < 250:
        return None
    profile = 'phone' if aspect >= 1.85 else 'tablet'
    height_ratio = .16 if profile == 'phone' else .115
    stop = min(height, round(min(height * height_ratio, width * .075)))
    search = pixels[:min(pixel_height, stop), :min(pixel_width, round(width * .78))]
    low, high = search.min(axis=2), search.max(axis=2)
    # Near-white text, not the bright colored weapon behind the title.
    mask = (low >= 200) & ((high.astype('int16') - low) < 55)
    active_rows = np.flatnonzero(mask.sum(axis=1) >= max(8, width * .012))
    if not len(active_rows):
        return None
    row_breaks = np.flatnonzero(np.diff(active_rows) > max(3, round(width * .004))) + 1
    for group in np.split(active_rows, row_breaks):
        y0, y1 = int(group[0]), int(group[-1]) + 1
        band_height = y1 - y0
        if not width * .015 <= band_height <= width * .065 or y0 > height * .07:
            continue
        columns = np.flatnonzero(mask[y0:y1].sum(axis=0) >= max(2, band_height * .12))
        if not len(columns):
            continue
        column_breaks = np.flatnonzero(np.diff(columns) > width * .065) + 1
        for segment in np.split(columns, column_breaks):
            x0, x1 = int(segment[0]), int(segment[-1]) + 1
            if x0 > width * .15 or x1 - x0 < width * .2:
                continue
            # A clipped title must not be used as a complete line.
            if x1 >= search.shape[1] - max(3, width * .005):
                return None
            pad_y, pad_x = max(3, round(band_height * .18)), max(3, round(band_height * .15))
            return {'box': (max(0, x0 - pad_x), max(0, y0 - pad_y),
                            min(pixel_width, x1 + pad_x), min(pixel_height, y1 + pad_y)),
                    'profile': profile}
    return None


def research_probe_box(width, height, profile):
    """A narrow research strip, used only after the original fast pass misses."""
    y0, y1 = (.126, .18) if profile == 'phone' else (.104, .149)
    return (0, int(height * y0), max(1, int(width * .25)), max(1, int(height * y1)))
