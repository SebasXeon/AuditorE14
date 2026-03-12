from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from PIL import Image
import os
import cv2
import numpy as np
from PIL import Image


@dataclass
class MassAnalysis:
    bbox: Tuple[int, int, int, int]
    suspicious: bool
    score: float
    median_radius: float
    p95_radius: float
    max_radius: float
    wide_area_ratio: float
    skeleton_pixels: int


def has_inconsistencies(image: Image.Image) -> bool:
    """
    Heuristic detector for possible overwrites / erasures in a handwritten row
    containing ~3 separated masses (digits, dashes, dots, circles, etc.).

    Returns:
        True if any mass looks suspicious enough to deserve manual review.

    Notes:
        - This is NOT proof of tampering.
        - It is a screening heuristic designed to catch abnormal localized
          stroke-thickness bulges that often appear when writing on top of
          a pre-existing dash/dot/mark.
    """
    gray = _pil_to_gray(image)
    binary = _binarize_dark_ink(gray)

    # Small cleanup: remove isolated dots/noise, keep strokes intact.
    kernel = np.ones((2, 2), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    masses = _segment_masses(binary)
    if not masses:
        return False

    analyses = [_analyze_mass(m) for m in masses]
    return any(a.suspicious for a in analyses)


# ---------- Core pipeline ----------

def _pil_to_gray(image: Image.Image) -> np.ndarray:
    arr = np.array(image.convert("L"))
    return arr


def _binarize_dark_ink(gray: np.ndarray) -> np.ndarray:
    """
    Returns a binary image with handwriting as 255 and background as 0.
    Uses Otsu + inversion because form backgrounds are usually light and ink dark.
    """
    # Light denoising before thresholding helps on scanned forms.
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # Otsu chooses threshold automatically on 8-bit single-channel images.
    _, binary_inv = cv2.threshold(
        blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    return binary_inv


def _segment_masses(binary: np.ndarray) -> List[np.ndarray]:
    """
    Split into horizontal masses using vertical projection.
    This works well when the row contains separated groups like:
        [ 12 ]   [ - ]   [ 9 ]
    or similar.
    """
    h, w = binary.shape
    col_sum = (binary > 0).sum(axis=0).astype(np.float32)

    if col_sum.max() == 0:
        return []

    # Smooth the projection to avoid tiny gaps splitting one mass into many.
    smooth = cv2.GaussianBlur(col_sum.reshape(1, -1), (1, 0), 0).ravel()

    # Dynamic threshold: treat columns with enough ink as occupied.
    occupied = smooth > max(1.0, 0.05 * smooth.max())

    runs = _runs_of_true(occupied)

    # Merge runs separated by very small blank gaps.
    merged = []
    min_gap = max(3, w // 80)
    for start, end in runs:
        if not merged:
            merged.append([start, end])
        else:
            prev_start, prev_end = merged[-1]
            if start - prev_end <= min_gap:
                merged[-1][1] = end
            else:
                merged.append([start, end])

    # Crop each mass tightly in both axes.
    masses = []
    for start, end in merged:
        sub = binary[:, start:end]
        ys, xs = np.where(sub > 0)
        if len(xs) == 0:
            continue

        x0 = max(0, xs.min() - 2)
        x1 = min(sub.shape[1], xs.max() + 3)
        y0 = max(0, ys.min() - 2)
        y1 = min(sub.shape[0], ys.max() + 3)

        crop = sub[y0:y1, x0:x1]
        if crop.size == 0:
            continue

        # Ignore tiny junk crops.
        if (crop > 0).sum() < 20:
            continue

        masses.append(crop)

    return masses


def _runs_of_true(mask: np.ndarray) -> List[Tuple[int, int]]:
    runs: List[Tuple[int, int]] = []
    in_run = False
    start = 0

    for i, v in enumerate(mask):
        if v and not in_run:
            start = i
            in_run = True
        elif not v and in_run:
            runs.append((start, i))
            in_run = False

    if in_run:
        runs.append((start, len(mask)))

    return runs


def _analyze_mass(binary_mass: np.ndarray) -> MassAnalysis:
    """
    Decide whether a single handwritten mass is suspicious based on
    localized thickness anomalies.
    """
    ink = (binary_mass > 0).astype(np.uint8)

    # Ignore degenerate masses.
    ink_pixels = int(ink.sum())
    if ink_pixels < 20:
        return MassAnalysis(
            bbox=(0, 0, binary_mass.shape[1], binary_mass.shape[0]),
            suspicious=False,
            score=0.0,
            median_radius=0.0,
            p95_radius=0.0,
            max_radius=0.0,
            wide_area_ratio=0.0,
            skeleton_pixels=0,
        )

    # Keep the main connected component(s). This reduces dust/noise.
    ink = _keep_relevant_components(ink)

    # Distance transform gives radius to nearest background for foreground pixels.
    dist = cv2.distanceTransform(ink, cv2.DIST_L2, 5)

    # Skeletonize so we sample thickness along stroke centerlines.
    skel = _zhang_suen_thinning(ink * 255)
    skel_mask = skel > 0

    skeleton_values = dist[skel_mask]
    skeleton_values = skeleton_values[skeleton_values > 0]

    if len(skeleton_values) < 8:
        return MassAnalysis(
            bbox=(0, 0, binary_mass.shape[1], binary_mass.shape[0]),
            suspicious=False,
            score=0.0,
            median_radius=0.0,
            p95_radius=0.0,
            max_radius=0.0,
            wide_area_ratio=0.0,
            skeleton_pixels=int(skel_mask.sum()),
        )

    median_r = float(np.median(skeleton_values))
    p95_r = float(np.percentile(skeleton_values, 95))
    max_r = float(np.max(skeleton_values))

    # Wide skeleton points = places where local stroke width is unusually large.
    # Overwriting on top of a dash/dot often creates localized bulges.
    wide_factor = 1.9
    wide_points = (dist > median_r * wide_factor) & skel_mask

    # Expand wide points a bit to form regions.
    wide_regions = cv2.dilate(
        wide_points.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1
    )

    # Compute how localized the anomaly is.
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        wide_regions, connectivity=8
    )

    large_region_pixels = 0
    region_count = 0
    for label in range(1, num_labels):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area >= 3:
            large_region_pixels += area
            region_count += 1

    wide_area_ratio = large_region_pixels / max(1, int(skel_mask.sum()))

    # Shape-independent anomaly score.
    # We want:
    # - noticeable tail in thickness values
    # - some localized abnormal region
    # - not just globally thick writing
    thickness_tail = p95_r / max(0.75, median_r)
    peak_factor = max_r / max(0.75, median_r)

    score = (
        0.55 * thickness_tail +
        0.35 * peak_factor +
        1.25 * wide_area_ratio +
        0.15 * region_count
    )

    # Conservative thresholds: flag only clearly odd masses.
    suspicious = (
        (thickness_tail >= 1.8 and peak_factor >= 2.2 and wide_area_ratio >= 0.03)
        or (score >= 3.3 and wide_area_ratio >= 0.02)
    )

    return MassAnalysis(
        bbox=(0, 0, binary_mass.shape[1], binary_mass.shape[0]),
        suspicious=bool(suspicious),
        score=float(score),
        median_radius=median_r,
        p95_radius=p95_r,
        max_radius=max_r,
        wide_area_ratio=float(wide_area_ratio),
        skeleton_pixels=int(skel_mask.sum()),
    )


# ---------- Utilities ----------

def _keep_relevant_components(ink: np.ndarray) -> np.ndarray:
    """
    Keep connected components that are not tiny dust.
    """
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        ink.astype(np.uint8), connectivity=8
    )

    if num_labels <= 1:
        return ink.astype(np.uint8)

    areas = stats[1:, cv2.CC_STAT_AREA]
    if len(areas) == 0:
        return ink.astype(np.uint8)

    max_area = int(areas.max())
    out = np.zeros_like(ink, dtype=np.uint8)

    for label in range(1, num_labels):
        area = int(stats[label, cv2.CC_STAT_AREA])
        # Keep reasonably meaningful components.
        if area >= max(6, int(max_area * 0.05)):
            out[labels == label] = 1

    return out


def _zhang_suen_thinning(binary_255: np.ndarray) -> np.ndarray:
    """
    Zhang-Suen thinning implementation.
    Input: binary image with foreground 255, background 0
    Output: skeleton binary image with foreground 255, background 0
    """
    img = (binary_255 > 0).astype(np.uint8)
    changed = True

    while changed:
        changed = False

        # Step 1
        to_remove = []
        rows, cols = img.shape
        for y in range(1, rows - 1):
            for x in range(1, cols - 1):
                P1 = img[y, x]
                if P1 != 1:
                    continue

                p2 = img[y - 1, x]
                p3 = img[y - 1, x + 1]
                p4 = img[y, x + 1]
                p5 = img[y + 1, x + 1]
                p6 = img[y + 1, x]
                p7 = img[y + 1, x - 1]
                p8 = img[y, x - 1]
                p9 = img[y - 1, x - 1]

                neighbors = [p2, p3, p4, p5, p6, p7, p8, p9]
                B = sum(neighbors)
                A = sum(
                    (neighbors[i] == 0 and neighbors[(i + 1) % 8] == 1)
                    for i in range(8)
                )

                if (
                    2 <= B <= 6
                    and A == 1
                    and p2 * p4 * p6 == 0
                    and p4 * p6 * p8 == 0
                ):
                    to_remove.append((y, x))

        if to_remove:
            changed = True
            for y, x in to_remove:
                img[y, x] = 0

        # Step 2
        to_remove = []
        for y in range(1, rows - 1):
            for x in range(1, cols - 1):
                P1 = img[y, x]
                if P1 != 1:
                    continue

                p2 = img[y - 1, x]
                p3 = img[y - 1, x + 1]
                p4 = img[y, x + 1]
                p5 = img[y + 1, x + 1]
                p6 = img[y + 1, x]
                p7 = img[y + 1, x - 1]
                p8 = img[y, x - 1]
                p9 = img[y - 1, x - 1]

                neighbors = [p2, p3, p4, p5, p6, p7, p8, p9]
                B = sum(neighbors)
                A = sum(
                    (neighbors[i] == 0 and neighbors[(i + 1) % 8] == 1)
                    for i in range(8)
                )

                if (
                    2 <= B <= 6
                    and A == 1
                    and p2 * p4 * p8 == 0
                    and p2 * p6 * p8 == 0
                ):
                    to_remove.append((y, x))

        if to_remove:
            changed = True
            for y, x in to_remove:
                img[y, x] = 0

    return (img * 255).astype(np.uint8)


current_dir = os.path.dirname(os.path.abspath(__file__))
tests_dir = os.path.join(current_dir, "tests")


# Iterate over all png in test folder
for filename in os.listdir(tests_dir):
    if filename.endswith(".png"):
        print(filename)
        im = Image.open(os.path.join(tests_dir, filename))
        if has_inconsistencies(im):
            print(f"Inconsistencies detected in {filename}")