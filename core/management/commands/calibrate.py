import cv2
import os
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from core.calibration_pipeline import CalibrationComputationError
from core.calibration_service import create_calibration_session
from core.models import Camera
from core.utils import open_camera


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

        lines = self._collect_line_points(image_path)
        if not lines:
            raise CommandError("No lines were recorded; calibration aborted.")

        try:
            create_calibration_session(camera, image_path, lines)
        except CalibrationComputationError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(
            "Calibration session captured. Review and accept it from the Django sheet page."
        ))

    def _capture_reference_frame(self, camera):
        cap = open_camera(camera.device_index)
        if not cap.isOpened():
            raise CommandError(f"Cannot open camera index {camera.device_index} for calibration capture")
        try:
            ret, frame = cap.read()
        finally:
            cap.release()
        if not ret:
            raise CommandError("Failed to grab frame from camera")

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

    def _collect_line_points(self, image_path):
        """Launches an interactive OpenCV window to collect line clicks."""
        img = cv2.imread(image_path)
        if img is None:
            raise CommandError(f"Unable to read image at {image_path}")

        window = 'Calibration - Click Lines'
        display = img.copy()
        current_line = []
        lines = []

        self.stdout.write("Mouse controls: left-click to add points, 'n' to store the current line, 's' to finish, ESC to abort.")

        def mouse_cb(event, x, y, _flags, _param):
            nonlocal current_line
            if event == cv2.EVENT_LBUTTONDOWN:
                current_line.append((x, y))
                cv2.circle(display, (x, y), 4, (0, 255, 0), -1)
                cv2.imshow(window, display)

        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(window, mouse_cb)
        cv2.imshow(window, display)

        while True:
            key = cv2.waitKey(20) & 0xFF
            if key == 27:  # ESC cancels
                lines = []
                break
            if key == ord('n'):
                if current_line:
                    lines.append(current_line)
                    current_line = []
            if key == ord('s'):
                if current_line:
                    lines.append(current_line)
                    current_line = []
                if lines:
                    break

        cv2.destroyAllWindows()
        return lines
