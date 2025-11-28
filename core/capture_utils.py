from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import cv2  # type: ignore[import]
import numpy as np
import requests
from django.conf import settings
from django.core.files.base import ContentFile

from .models import Camera, CapturedFrame
from .utils import open_camera

CAPTURED_FRAMES_DIR = os.path.join(settings.BASE_DIR, 'captured_frames')
LATEST_FRAME_ALIAS = 'latest_frame.jpg'


class CameraFrameSource:
    """Abstracts how frames are retrieved so cameras can use USB or HTTP."""

    def __init__(self, camera: Camera, snapshot_timeout: float = 5.0) -> None:
        self.camera = camera
        self.snapshot_timeout = snapshot_timeout
        self._cap: Optional[cv2.VideoCapture] = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()

    def open(self) -> None:
        if self.camera.snapshot_url:
            return
        if self.camera.device_index is None:
            raise RuntimeError("Camera has no device index configured and snapshot URL is empty.")
        self._cap = open_camera(self.camera.device_index)
        if not self._cap.isOpened():
            self.release()
            raise RuntimeError(f"Cannot open camera index {self.camera.device_index}.")

    def read(self):
        if self.camera.snapshot_url:
            return self._read_http_frame(self.camera.snapshot_url)
        if not self._cap:
            raise RuntimeError("Video capture device was not opened correctly.")
        ret, frame = self._cap.read()
        if not ret:
            raise RuntimeError("Failed to grab a frame from the selected camera.")
        return frame

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _read_http_frame(self, url: str):
        try:
            response = requests.get(url, timeout=self.snapshot_timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Failed to fetch snapshot from {url}: {exc}") from exc
        buffer = np.frombuffer(response.content, dtype=np.uint8)
        frame = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if frame is None:
            raise RuntimeError("Snapshot endpoint did not return a valid image.")
        return frame


def capture_single_frame(camera):
    """Grab a single frame from the given camera and persist it for calibration."""
    with CameraFrameSource(camera) as source:
        frame = source.read()

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
