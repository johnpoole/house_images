import cv2
import json
import os
from datetime import datetime
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from core.models import Camera, CalibrationArtifact


CAPTURED_FRAMES_DIR = os.path.join(settings.BASE_DIR, 'captured_frames')
LATEST_FRAME_ALIAS = 'latest_frame.jpg'

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
            
        # Define calibration directory
        calib_dir = os.path.join("calibration", f"sheet{sheet_num}_{side}")
        os.makedirs(calib_dir, exist_ok=True)
        
        self.stdout.write(self.style.SUCCESS(f"Starting calibration for {camera}"))
        self.stdout.write(f"Output directory: {calib_dir}")
        image_path = options.get('image')
        if image_path:
            if not os.path.exists(image_path):
                raise CommandError(f"Could not find reference image at {image_path}")
        else:
            image_path = self._capture_reference_frame(camera, calib_dir)

        lines = self._collect_line_points(image_path)
        if not lines:
            raise CommandError("No lines were recorded; calibration aborted.")

        serialized_lines = [[[int(pt[0]), int(pt[1])] for pt in line] for line in lines]
        artifact_payload = {'lines': serialized_lines}

        lines_file = os.path.join(calib_dir, f"line_points_{camera.id}.json")
        with open(lines_file, 'w', encoding='utf-8') as handle:
            json.dump(artifact_payload, handle, indent=2)

        artifact = CalibrationArtifact.objects.create(
            camera=camera,
            artifact_type=CalibrationArtifact.ArtifactType.LINE_POINTS,
            data=artifact_payload,
            source_image_path=os.path.abspath(image_path),
            artifact_file=os.path.abspath(lines_file),
            notes=f"Collected {len(lines)} line(s) via calibrate command"
        )

        camera.calibration_dir = calib_dir
        camera.is_calibrated = True
        camera.save()

        self.stdout.write(self.style.SUCCESS(f"Stored line clicks in {lines_file} and DB artifact #{artifact.id}"))
        self.stdout.write(self.style.SUCCESS(f"Updated camera record. Calibration dir: {calib_dir}"))

    def _capture_reference_frame(self, camera, calib_dir):
        cap = cv2.VideoCapture(camera.device_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            raise CommandError(f"Cannot open camera index {camera.device_index} for calibration capture")
        try:
            ret, frame = cap.read()
        finally:
            cap.release()
        if not ret:
            raise CommandError("Failed to grab frame from camera")

        os.makedirs(calib_dir, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        capture_path = os.path.join(calib_dir, f'calibration_frame_{ts}.jpg')
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
