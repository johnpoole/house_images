from __future__ import annotations

import os
from datetime import datetime

import cv2  # type: ignore[import]
from django.conf import settings
from django.core.files.base import ContentFile

from .models import CapturedFrame
from .utils import open_camera

CAPTURED_FRAMES_DIR = os.path.join(settings.BASE_DIR, 'captured_frames')
LATEST_FRAME_ALIAS = 'latest_frame.jpg'


def capture_single_frame(camera):
    """Grab a single frame from the given camera and persist it for calibration."""
    cap = open_camera(camera.device_index)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera index {camera.device_index}.")
    try:
        ret, frame = cap.read()
    finally:
        cap.release()
    if not ret:
        raise RuntimeError("Failed to grab a frame from the selected camera.")

    os.makedirs(CAPTURED_FRAMES_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    raw_name = f"sheet{camera.sheet.number}_{camera.side}_{timestamp}.jpg"
    raw_disk_path = os.path.join(CAPTURED_FRAMES_DIR, raw_name)
    cv2.imwrite(raw_disk_path, frame)
    cv2.imwrite(os.path.join(CAPTURED_FRAMES_DIR, LATEST_FRAME_ALIAS), frame)

    success, buffer = cv2.imencode('.jpg', frame)
    if not success:
        raise RuntimeError("Failed to encode captured frame to JPEG.")

    return CapturedFrame.objects.create(
        camera=camera,
        image=ContentFile(buffer.tobytes(), name=f"raw/{raw_name}"),
    )
