import cv2
import json
import numpy as np
import os
import time
from datetime import datetime
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from core.capture_utils import CameraFrameSource
from core.models import Camera, CapturedFrame


CAPTURED_FRAMES_DIR = os.path.join(settings.BASE_DIR, 'captured_frames')
RECTIFIED_SUBDIR = 'rectified'
LATEST_FRAME_ALIAS = 'latest_frame.jpg'
LATEST_RECTIFIED_ALIAS = 'latest_rectified.jpg'
COMPARE_SIZE = (320, 180)


class FrameCropper:
    def __init__(self, crop_rect_path):
        rect = np.load(crop_rect_path).reshape(-1)
        if rect.size != 4:
            raise ValueError(f"Crop rectangle at {crop_rect_path} must have four entries (x, y, w, h)")
        self.x, self.y, self.w, self.h = [int(v) for v in rect]

    def __call__(self, frame):
        return frame[self.y:self.y + self.h, self.x:self.x + self.w]


class FrameRectifier:
    def __init__(
        self,
        camera_matrix_path,
        dist_coeffs_path,
        new_camera_matrix_path,
        homography_path,
        output_size,
        cropper=None,
    ):
        self.K = np.load(camera_matrix_path)
        self.dist = np.load(dist_coeffs_path)
        self.newK = np.load(new_camera_matrix_path)
        self.H = np.load(homography_path)
        self.output_size = output_size
        self.cropper = cropper

    def __call__(self, frame):
        target_size = self.output_size or (frame.shape[1], frame.shape[0])
        undistorted = cv2.undistort(frame, self.K, self.dist, None, self.newK)
        warped = cv2.warpPerspective(undistorted, self.H, target_size)
        if self.cropper:
            warped = self.cropper(warped)
        return warped

class Command(BaseCommand):
    help = 'Runs the video capture loop for a specific camera'

    def add_arguments(self, parser):
        parser.add_argument('--sheet', type=int, required=True, help='Sheet number')
        parser.add_argument('--camera', type=str, required=True, choices=['odd', 'even'], help='Camera side (odd/even)')
        parser.add_argument('--poll-interval', type=float, default=1.0, help='Seconds between checks')
        parser.add_argument('--threshold', type=float, default=5.0, help='Pixel difference threshold')
        parser.add_argument('--max-frames', type=int, default=0, help='Stop after saving this many frames (0 = run indefinitely)')

    def handle(self, *args, **options):
        sheet_num = options['sheet']
        side = options['camera']

        try:
            camera = Camera.objects.get(sheet__number=sheet_num, side=side)
        except Camera.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Camera for Sheet {sheet_num} ({side}) not found in DB"))
            return

        if camera.snapshot_url:
            self.stdout.write(self.style.SUCCESS(f"Starting capture for {camera} via HTTP {camera.snapshot_url}"))
        elif camera.device_index is not None:
            self.stdout.write(self.style.SUCCESS(f"Starting capture for {camera} on device {camera.device_index}"))
        else:
            self.stderr.write(self.style.ERROR("Camera is missing both a device index and snapshot URL."))
            return

        frame_source = CameraFrameSource(camera)
        try:
            frame_source.open()
        except RuntimeError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        rectifier = self._build_rectifier(camera)
        if rectifier:
            self.stdout.write(self.style.SUCCESS("Calibrated pipeline loaded; rectified frames will be saved."))
        else:
            if camera.is_calibrated:
                self.stdout.write(self.style.WARNING("Camera marked calibrated but required files were missing; saving raw frames only."))

        prev_gray = None
        saved_frames = 0

        try:
            while True:
                try:
                    frame = frame_source.read()
                except RuntimeError as exc:
                    self.stderr.write(self.style.WARNING(str(exc)))
                    time.sleep(options['poll_interval'])
                    continue

                gray = cv2.cvtColor(cv2.resize(frame, COMPARE_SIZE), cv2.COLOR_BGR2GRAY)

                save_it = False
                mean_diff = None
                if prev_gray is None:
                    save_it = True
                else:
                    diff = cv2.absdiff(gray, prev_gray)
                    mean_diff = float(diff.mean())
                    if mean_diff >= options['threshold']:
                        save_it = True
                        self.stdout.write(f"Change detected: {mean_diff:.2f}")

                if save_it:
                    rectified_frame = rectifier(frame) if rectifier else None
                    self._persist_frame(camera, frame, rectified_frame)
                    prev_gray = gray
                    saved_frames += 1
                    if options['max_frames'] > 0 and saved_frames >= options['max_frames']:
                        self.stdout.write(self.style.SUCCESS("Reached max frame count; stopping."))
                        break

                time.sleep(options['poll_interval'])

        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS("Stopping capture"))
        finally:
            frame_source.release()

    def _build_rectifier(self, camera):
        if not camera.is_calibrated or not camera.calibration_dir:
            return None

        base = camera.calibration_dir
        paths = {
            'camera_matrix': os.path.join(base, 'camera_matrix.npy'),
            'dist_coeffs': os.path.join(base, 'dist_coeffs.npy'),
            'new_camera_matrix': os.path.join(base, 'new_camera_matrix.npy'),
            'homography': os.path.join(base, 'homography.npy'),
        }
        missing = [label for label, path in paths.items() if not os.path.exists(path)]
        if missing:
            missing_str = ', '.join(missing)
            self.stdout.write(self.style.WARNING(f"Missing calibration files ({missing_str}); skipping rectification."))
            return None

        crop_path = os.path.join(base, 'crop_rect.npy')
        cropper = FrameCropper(crop_path) if os.path.exists(crop_path) else None
        output_size = self._resolve_output_size(base)
        return FrameRectifier(
            camera_matrix_path=paths['camera_matrix'],
            dist_coeffs_path=paths['dist_coeffs'],
            new_camera_matrix_path=paths['new_camera_matrix'],
            homography_path=paths['homography'],
            output_size=output_size,
            cropper=cropper,
        )

    def _resolve_output_size(self, calib_dir):
        size_json = os.path.join(calib_dir, 'rectified_size.json')
        if os.path.exists(size_json):
            with open(size_json, 'r', encoding='utf-8') as handle:
                data = json.load(handle)
            try:
                return int(data['width']), int(data['height'])
            except (KeyError, TypeError, ValueError):
                return None
        return None

    def _persist_frame(self, camera, raw_frame, rectified_frame):
        os.makedirs(CAPTURED_FRAMES_DIR, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        raw_name = f"sheet{camera.sheet.number}_{camera.side}_{timestamp}.jpg"
        rect_name = f"sheet{camera.sheet.number}_{camera.side}_{timestamp}_rectified.jpg"

        raw_disk_path = os.path.join(CAPTURED_FRAMES_DIR, raw_name)
        cv2.imwrite(raw_disk_path, raw_frame)
        cv2.imwrite(os.path.join(CAPTURED_FRAMES_DIR, LATEST_FRAME_ALIAS), raw_frame)

        raw_success, raw_buffer = cv2.imencode('.jpg', raw_frame)
        if not raw_success:
            self.stderr.write(self.style.ERROR("Failed to encode raw frame; skipping save."))
            return

        rectified_content = None
        if rectified_frame is not None:
            rect_dir = os.path.join(CAPTURED_FRAMES_DIR, RECTIFIED_SUBDIR)
            os.makedirs(rect_dir, exist_ok=True)
            cv2.imwrite(os.path.join(rect_dir, rect_name), rectified_frame)
            cv2.imwrite(os.path.join(rect_dir, LATEST_RECTIFIED_ALIAS), rectified_frame)

            rect_success, rect_buffer = cv2.imencode('.jpg', rectified_frame)
            if rect_success:
                rectified_content = ContentFile(rect_buffer.tobytes(), name=f"{RECTIFIED_SUBDIR}/{rect_name}")
            else:
                self.stderr.write(self.style.WARNING("Rectified frame encode failed; raw frame saved only."))

        frame_kwargs = {
            'camera': camera,
            'image': ContentFile(raw_buffer.tobytes(), name=f"raw/{raw_name}")
        }
        if rectified_content:
            frame_kwargs['rectified_image'] = rectified_content

        CapturedFrame.objects.create(**frame_kwargs)
        self.stdout.write(self.style.SUCCESS(f"Saved frame {raw_name}{' (+rectified)' if rectified_content else ''}"))
