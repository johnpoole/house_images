from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

import cv2
import numpy as np


Point = Tuple[float, float]
Line = Sequence[Point]


@dataclass
class CalibrationResult:
    camera_matrix: np.ndarray
    dist_coeffs: np.ndarray
    new_camera_matrix: np.ndarray
    undistorted_image: np.ndarray
    cropped_image: np.ndarray
    crop_rect: Tuple[int, int, int, int]
    fit_error: float
    best_combo: Tuple[float, float, float]


class CalibrationComputationError(RuntimeError):
    """Raised when the calibration pipeline cannot produce a result."""


def _line_rms(points: np.ndarray) -> float:
    """Returns RMS distance of points from their best-fit line."""
    if points.shape[0] < 2:
        return 0.0
    mean = points.mean(axis=0)
    centered = points - mean
    _, _, vt = np.linalg.svd(centered)
    orth = vt[1]
    distances = centered @ orth
    return float(np.sqrt((distances * distances).mean()))


def _evaluate_params(
    pts_list: List[np.ndarray],
    image_shape: Tuple[int, int],
    f_factor: float,
    k1: float,
    k2: float,
) -> Tuple[float, np.ndarray, np.ndarray]:
    h, w = image_shape
    base = float(max(w, h))
    f = f_factor * base
    cx = w / 2.0
    cy = h / 2.0
    K = np.array([[f, 0.0, cx], [0.0, f, cy], [0.0, 0.0, 1.0]], dtype=np.float32)
    dist = np.array([k1, k2, 0.0, 0.0, 0.0], dtype=np.float32)

    total = 0.0
    for pts in pts_list:
        reshaped = pts.reshape(-1, 1, 2)
        und = cv2.undistortPoints(reshaped, K, dist, P=K).reshape(-1, 2)
        total += _line_rms(und)
    return total, K, dist


def _compute_crop_rect(
    lines: List[np.ndarray],
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    new_camera_matrix: np.ndarray,
    undistorted_shape: Tuple[int, int, int],
) -> Tuple[int, int, int, int]:
    all_points = []
    for pts in lines:
        reshaped = pts.reshape(-1, 1, 2)
        und = cv2.undistortPoints(reshaped, camera_matrix, dist_coeffs, P=new_camera_matrix).reshape(-1, 2)
        all_points.append(und)
    if not all_points:
        raise CalibrationComputationError("No points available to compute crop rectangle")

    stacked = np.vstack(all_points).astype(np.float32)
    hull = cv2.convexHull(stacked)
    x, y, w, h = cv2.boundingRect(hull)

    img_h, img_w = undistorted_shape[:2]
    x = max(0, min(x, img_w - 1))
    y = max(0, min(y, img_h - 1))
    w = max(1, min(w, img_w - x))
    h = max(1, min(h, img_h - y))
    return int(x), int(y), int(w), int(h)


def run_calibration_pipeline(
    image_path: str,
    lines: Iterable[Line],
    *,
    f_factors: Sequence[float] | None = None,
    k1_values: Sequence[float] | None = None,
    k2_values: Sequence[float] | None = None,
) -> CalibrationResult:
    """Runs the undistort+crop pipeline and returns all intermediate artifacts."""

    img = cv2.imread(image_path)
    if img is None:
        raise CalibrationComputationError(f"Unable to read calibration image at {image_path}")

    converted: List[np.ndarray] = []
    for line in lines:
        pts = np.array(line, dtype=np.float32)
        if pts.size == 0:
            continue
        converted.append(pts)
    if not converted:
        raise CalibrationComputationError("No calibration lines supplied")

    if f_factors is None:
        f_factors = [0.7, 0.8, 0.9, 1.0, 1.1]
    if k1_values is None:
        k1_values = [-0.30, -0.20, -0.15, -0.10, -0.05, 0.0]
    if k2_values is None:
        k2_values = [-0.10, -0.05, 0.0, 0.05]

    best_err = None
    best_combo = None
    best_K = None
    best_dist = None

    h, w = img.shape[:2]

    for f_factor in f_factors:
        for k1 in k1_values:
            for k2 in k2_values:
                err, K, dist = _evaluate_params(converted, (h, w), f_factor, k1, k2)
                if best_err is None or err < best_err:
                    best_err = err
                    best_combo = (f_factor, k1, k2)
                    best_K = K
                    best_dist = dist

    if best_K is None or best_dist is None or best_err is None or best_combo is None:
        raise CalibrationComputationError("Failed to determine camera parameters")

    new_K, _ = cv2.getOptimalNewCameraMatrix(best_K, best_dist, (w, h), 1.0)
    undistorted = cv2.undistort(img, best_K, best_dist, None, new_K)

    crop_rect = _compute_crop_rect(converted, best_K, best_dist, new_K, undistorted.shape)
    x, y, cw, ch = crop_rect
    cropped = undistorted[y : y + ch, x : x + cw]

    return CalibrationResult(
        camera_matrix=best_K,
        dist_coeffs=best_dist,
        new_camera_matrix=new_K,
        undistorted_image=undistorted,
        cropped_image=cropped,
        crop_rect=crop_rect,
        fit_error=best_err,
        best_combo=best_combo,
    )
