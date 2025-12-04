import os
from typing import Iterable, List, Sequence

import cv2
import numpy as np
from django.conf import settings
from django.core.files import File
from django.db import transaction

from .auto_calibration import generate_auto_calibration
from .calibration_pipeline import CalibrationComputationError, run_calibration_pipeline
from .models import CalibrationLinePoint, CalibrationSession

SESSION_OUTPUT_ROOT = os.path.join(settings.BASE_DIR, 'calibration', 'sessions')


def _normalize_lines(lines: Iterable[Sequence[Sequence[float]]]) -> List[List[tuple[int, int]]]:
    normalized: List[List[tuple[int, int]]] = []
    for line in lines:
        converted = []
        for point in line:
            if len(point) < 2:
                continue
            x, y = int(round(point[0])), int(round(point[1]))
            converted.append((x, y))
        if converted:
            normalized.append(converted)
    return normalized


def create_calibration_session(
    camera,
    image_path: str,
    lines: Iterable[Sequence[Sequence[float]]] | None = None,
):
    auto_features = {}
    if lines is None:
        auto_result = generate_auto_calibration(image_path)
        lines = auto_result.lines
        auto_features = auto_result.features

    cleaned_lines = _normalize_lines(lines)
    if not cleaned_lines:
        raise CalibrationComputationError('No calibration lines supplied.')

    with transaction.atomic():
        session = CalibrationSession.objects.create(camera=camera)

    _attach_source_image(session, image_path)
    _persist_line_points(session, cleaned_lines)

    result = run_calibration_pipeline(image_path, cleaned_lines)
    artifact_dir = _write_session_artifacts(session, result)
    rel_dir = os.path.relpath(artifact_dir, settings.BASE_DIR)

    x, y, w, h = result.crop_rect
    session.fit_error = result.fit_error
    session.crop_rect = {'x': int(x), 'y': int(y), 'w': int(w), 'h': int(h)}
    metadata = {
        'best_combo': result.best_combo,
        'line_count': len(cleaned_lines),
    }
    if auto_features:
        metadata['auto_features'] = auto_features
    session.metadata = metadata
    session.artifact_dir = rel_dir
    session.save(update_fields=['fit_error', 'crop_rect', 'metadata', 'artifact_dir'])

    return session


def _attach_source_image(session, image_path: str):
    with open(image_path, 'rb') as handle:
        session.source_image.save(os.path.basename(image_path), File(handle), save=True)


def _persist_line_points(session, lines: List[List[tuple[int, int]]]):
    records = []
    for line_index, line in enumerate(lines):
        for point_index, (x, y) in enumerate(line):
            records.append(
                CalibrationLinePoint(
                    session=session,
                    line_index=line_index,
                    point_index=point_index,
                    x=x,
                    y=y,
                )
            )
    CalibrationLinePoint.objects.bulk_create(records)


def _write_session_artifacts(session, result):
    session_dir = os.path.join(SESSION_OUTPUT_ROOT, f'session_{session.id}')
    os.makedirs(session_dir, exist_ok=True)

    np.save(os.path.join(session_dir, 'camera_matrix.npy'), result.camera_matrix)
    np.save(os.path.join(session_dir, 'dist_coeffs.npy'), result.dist_coeffs)
    np.save(os.path.join(session_dir, 'new_camera_matrix.npy'), result.new_camera_matrix)
    np.save(os.path.join(session_dir, 'crop_rect.npy'), np.array(result.crop_rect, dtype=np.int32))

    undist_path = os.path.join(session_dir, 'undistorted_preview.jpg')
    rectified_path = os.path.join(session_dir, 'rectified_preview.jpg')
    cv2.imwrite(undist_path, result.undistorted_image)
    cv2.imwrite(rectified_path, result.cropped_image)

    with open(rectified_path, 'rb') as handle:
        session.rectified_preview.save(os.path.basename(rectified_path), File(handle), save=True)

    return session_dir
