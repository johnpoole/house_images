import cv2
import os
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from core.calibration_pipeline import CalibrationComputationError
from core.calibration_service import create_calibration_session
from core.capture_utils import CameraFrameSource
from core.models import Camera


CAPTURED_FRAMES_DIR = os.path.join(settings.BASE_DIR, 'captured_frames')
LATEST_FRAME_ALIAS = 'latest_frame.jpg'
SESSION_OUTPUT_ROOT = os.path.join(settings.BASE_DIR, 'calibration', 'sessions')

class Command(BaseCommand):
    help = 'Runs interactive calibration for a camera'

    def add_arguments(self, parser):
        parser.add_argument('--sheet', type=int, required=True, help='Sheet number')
        parser.add_argument('--camera', type=str, required=True, choices=['odd', 'even'], help='Camera side (odd/even)')
        parser.add_argument('--image', type=str, help='Use an existing image path instead of capturing a fresh frame')

    def handle(self, *args, **options):
        sheet_num = options['sheet']
        side = options['camera']

        try:
            camera = Camera.objects.get(sheet__number=sheet_num, side=side)
        except Camera.DoesNotExist as exc:
            raise CommandError(f"Camera for Sheet {sheet_num} ({side}) not found in DB") from exc

        self.stdout.write(self.style.SUCCESS(f"Starting calibration for {camera}"))
        image_path = options.get('image')
        if image_path:
            if not os.path.exists(image_path):
                raise CommandError(f"Could not find reference image at {image_path}")
        else:
            image_path = self._capture_reference_frame(camera)

        try:
            session = create_calibration_session(camera, image_path)
        except CalibrationComputationError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(
            f"Auto-calibration session {session.id} captured. Review and accept it from the Django sheet page."
        ))

    def _capture_reference_frame(self, camera):
        try:
            with CameraFrameSource(camera) as source:
                frame = source.read()
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        capture_dir = os.path.join(SESSION_OUTPUT_ROOT, 'captures')
        os.makedirs(capture_dir, exist_ok=True)
        capture_path = os.path.join(capture_dir, f'sheet{camera.sheet.number}_{camera.side}_{ts}.jpg')
        cv2.imwrite(capture_path, frame)

        os.makedirs(CAPTURED_FRAMES_DIR, exist_ok=True)
        latest_path = os.path.join(CAPTURED_FRAMES_DIR, LATEST_FRAME_ALIAS)
        cv2.imwrite(latest_path, frame)
        self.stdout.write(f"Stored reference frame at {capture_path} (latest alias updated)")
        return capture_path

    # Manual tracing removed; calibration is now fully automatic.
