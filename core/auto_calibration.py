from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import cv2
import numpy as np

from .calibration_pipeline import CalibrationComputationError

PointList = List[Tuple[int, int]]

# World Curling Federation sheet dimensions (feet)
SHEET_WIDTH_FT = 14.5
SHEET_LENGTH_FT = 146.0
BACKLINE_OFFSET_FT = 10.0
TEELINE_OFFSET_FT = 16.0
HOGLINE_OFFSET_FT = 37.0
HOUSE_RADII_FT = [
    ("12ft", 6.0),
    ("8ft", 4.0),
    ("4ft", 2.0),
    ("button", 0.5),
]

@dataclass
class AutoCalibrationResult:
    lines: List[PointList]
    features: Dict[str, object]


def generate_auto_calibration(image_path: str) -> AutoCalibrationResult:
    image = cv2.imread(image_path)
    if image is None:
        raise CalibrationComputationError(f"Unable to read calibration image at {image_path}")

    corners = _detect_sheet_corners(image)
    homography = _build_homography(corners)

    reference_lines = _build_reference_lines(homography)
    features = _summarize_features(corners, homography, reference_lines)

    return AutoCalibrationResult(lines=list(reference_lines.values()), features=features)


def _detect_sheet_corners(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 25, 75)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise CalibrationComputationError("Unable to find sheet outline in calibration image")

    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approx) == 4:
            return _order_points(approx.reshape(4, 2).astype(np.float32))

    rect = cv2.minAreaRect(contours[0])
    box = cv2.boxPoints(rect)
    return _order_points(box.astype(np.float32))


def _order_points(points: np.ndarray) -> np.ndarray:
    ordered = np.zeros((4, 2), dtype=np.float32)
    s = points.sum(axis=1)
    diff = np.diff(points, axis=1)

    ordered[0] = points[np.argmin(s)]  # top-left
    ordered[2] = points[np.argmax(s)]  # bottom-right
    ordered[1] = points[np.argmin(diff)]  # top-right
    ordered[3] = points[np.argmax(diff)]  # bottom-left
    return ordered


def _build_homography(corners: np.ndarray) -> np.ndarray:
    canonical = np.array(
        [
            [0.0, 0.0],
            [SHEET_WIDTH_FT, 0.0],
            [SHEET_WIDTH_FT, SHEET_LENGTH_FT],
            [0.0, SHEET_LENGTH_FT],
        ],
        dtype=np.float32,
    )
    return cv2.getPerspectiveTransform(canonical, corners)


def _build_reference_lines(homography: np.ndarray) -> Dict[str, PointList]:
    lines: Dict[str, PointList] = {}
    center_x = SHEET_WIDTH_FT / 2.0
    lines["center_line"] = _vertical_line(homography, center_x)

    lines["hog_far"] = _horizontal_line(homography, HOGLINE_OFFSET_FT)
    lines["hog_near"] = _horizontal_line(homography, SHEET_LENGTH_FT - HOGLINE_OFFSET_FT)

    lines["tee_far"] = _horizontal_line(homography, TEELINE_OFFSET_FT)
    lines["tee_near"] = _horizontal_line(homography, SHEET_LENGTH_FT - TEELINE_OFFSET_FT)

    lines["back_far"] = _horizontal_line(homography, BACKLINE_OFFSET_FT)
    lines["back_near"] = _horizontal_line(homography, SHEET_LENGTH_FT - BACKLINE_OFFSET_FT)
    return lines


def _vertical_line(homography: np.ndarray, x_ft: float, samples: int = 200) -> PointList:
    ys = np.linspace(0.0, SHEET_LENGTH_FT, samples)
    canonical = np.column_stack([np.full_like(ys, x_ft), ys])
    return _project_to_points(homography, canonical)


def _horizontal_line(homography: np.ndarray, y_ft: float, samples: int = 160) -> PointList:
    xs = np.linspace(0.0, SHEET_WIDTH_FT, samples)
    canonical = np.column_stack([xs, np.full_like(xs, y_ft)])
    return _project_to_points(homography, canonical)


def _project_to_points(homography: np.ndarray, canonical_points: np.ndarray) -> PointList:
    pts = canonical_points.astype(np.float32).reshape(-1, 1, 2)
    projected = cv2.perspectiveTransform(pts, homography).reshape(-1, 2)
    rounded = np.rint(projected).astype(int)
    return [(int(pt[0]), int(pt[1])) for pt in rounded]


def _line_endpoints(points: Sequence[Tuple[int, int]]) -> Dict[str, List[int]]:
    return {
        "start": [int(points[0][0]), int(points[0][1])],
        "end": [int(points[-1][0]), int(points[-1][1])],
    }


def _summarize_features(
    corners: np.ndarray,
    homography: np.ndarray,
    lines: Dict[str, PointList],
) -> Dict[str, object]:
    features: Dict[str, object] = {
        "sheet_corners": corners.round().astype(int).tolist(),
        "center_line": _line_endpoints(lines["center_line"]),
        "hog_lines": {
            "far": _line_endpoints(lines["hog_far"]),
            "near": _line_endpoints(lines["hog_near"]),
        },
        "tee_lines": {
            "far": _line_endpoints(lines["tee_far"]),
            "near": _line_endpoints(lines["tee_near"]),
        },
        "back_lines": {
            "far": _line_endpoints(lines["back_far"]),
            "near": _line_endpoints(lines["back_near"]),
        },
    }

    house_features = []
    for end_label, center_y in ("far", TEELINE_OFFSET_FT), ("near", SHEET_LENGTH_FT - TEELINE_OFFSET_FT):
        center_pt = _project_to_points(
            homography,
            np.array([[SHEET_WIDTH_FT / 2.0, center_y]], dtype=np.float32),
        )[0]
        for name, radius_ft in HOUSE_RADII_FT:
            edge_point = _project_to_points(
                homography,
                np.array([[SHEET_WIDTH_FT / 2.0 + radius_ft, center_y]], dtype=np.float32),
            )[0]
            radius_px = int(round(float(np.linalg.norm(np.array(center_pt) - np.array(edge_point)))))
            house_features.append(
                {
                    "end": end_label,
                    "name": name,
                    "center": [int(center_pt[0]), int(center_pt[1])],
                    "radius_px": radius_px,
                }
            )
    features["house_circles"] = house_features
    return features
