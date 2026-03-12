from __future__ import annotations

import cv2
import numpy as np
from PIL import Image
import os


def _pil_to_gray_np(image: Image.Image) -> np.ndarray:
    rgb = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    return gray


def _merge_near_duplicates(
    boxes: list[tuple[int, int, int, int]],
    y_tol: int = 12,
    x_tol: int = 12,
    w_tol: int = 20,
    h_tol: int = 20,
) -> list[tuple[int, int, int, int]]:
    """
    Merge almost-identical boxes caused by scan artifacts or double contours.
    """
    if not boxes:
        return []

    boxes = sorted(boxes, key=lambda b: (b[1], b[0]))
    merged: list[tuple[int, int, int, int]] = []

    for box in boxes:
        x, y, w, h = box
        matched = False

        for i, (mx, my, mw, mh) in enumerate(merged):
            if (
                abs(x - mx) <= x_tol
                and abs(y - my) <= y_tol
                and abs(w - mw) <= w_tol
                and abs(h - mh) <= h_tol
            ):
                nx = min(x, mx)
                ny = min(y, my)
                nr = max(x + w, mx + mw)
                nb = max(y + h, my + mh)
                merged[i] = (nx, ny, nr - nx, nb - ny)
                matched = True
                break

        if not matched:
            merged.append(box)

    return merged


def get_candidate_boxes(image: Image.Image) -> list[Image.Image]:
    """
    Detect candidate rectangles from a scanned election form and return them as cropped PIL images.

    Detection logic is based on:
    - dark outlined boxes on white background
    - candidate boxes occupy most of the page width
    - candidate boxes are stacked vertically in the lower part of the form
    - robust against page downscaling and very small rotation

    Returns:
        list[Image.Image]
    """
    gray = _pil_to_gray_np(image)
    page_h, page_w = gray.shape

    # Binarize: dark ink/lines become white foreground
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    # Light closing helps reconnect slightly broken border lines
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    processed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)

    # Only external contours: candidate boxes are outer containers
    contours, _ = cv2.findContours(
        processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    found_boxes: list[tuple[int, int, int, int]] = []

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)

        # Relative dimensions instead of fixed pixels
        width_ratio = w / page_w
        height_ratio = h / page_h
        y_ratio = y / page_h

        # These values fit the sample form and similar scans:
        # - candidate rows are ~87% of page width
        # - row height is ~8% of page height
        # - rows are below the form header
        if not (0.82 <= width_ratio <= 0.95):
            continue
        if not (0.07 <= height_ratio <= 0.11):
            continue
        if y_ratio < 0.25:
            continue

        found_boxes.append((x, y, w, h))

    # Merge near-duplicates and sort top-to-bottom
    found_boxes = _merge_near_duplicates(found_boxes)
    found_boxes.sort(key=lambda b: (b[1], b[0]))

    # Crop with tiny padding
    rgb = np.array(image.convert("RGB"))
    results: list[Image.Image] = []

    for x, y, w, h in found_boxes:
        pad = 3
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(page_w, x + w + pad)
        y2 = min(page_h, y + h + pad)

        crop = rgb[y1:y2, x1:x2]
        results.append(Image.fromarray(crop))

    return results



current_dir = os.path.dirname(os.path.abspath(__file__))
im = Image.open(os.path.join(current_dir, "test.png"))
candidates = get_candidate_boxes(im)
print(f"Found {len(candidates)} candidate boxes.")
for i, candidate in enumerate(candidates):
    candidate.save(os.path.join(current_dir, "tests", "found", f"candidate_{i}.png"))