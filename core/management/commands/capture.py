import cv2
import numpy as np
import time
import os
from datetime import datetime
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.conf import settings
from core.models import Camera, CapturedFrame

class Command(BaseCommand):
    help = 'Runs the video capture loop for a specific camera'

    def add_arguments(self, parser):
        parser.add_argument('--sheet', type=int, required=True, help='Sheet number')
        parser.add_argument('--camera', type=str, required=True, choices=['odd', 'even'], help='Camera side (odd/even)')
        parser.add_argument('--poll-interval', type=float, default=1.0, help='Seconds between checks')
        parser.add_argument('--threshold', type=float, default=5.0, help='Pixel difference threshold')

    def handle(self, *args, **options):
        sheet_num = options['sheet']
        side = options['camera']
        
        try:
            camera = Camera.objects.get(sheet__number=sheet_num, side=side)
        except Camera.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Camera for Sheet {sheet_num} ({side}) not found in DB"))
            return

        self.stdout.write(self.style.SUCCESS(f"Starting capture for {camera} on device {camera.device_index}"))

        cap = cv2.VideoCapture(camera.device_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            self.stderr.write(self.style.ERROR(f"Could not open camera index {camera.device_index}"))
            return

        # TODO: Load calibration data if camera.is_calibrated and camera.calibration_dir exists
        # For now, we just capture raw frames to get the pipeline working

        prev_gray = None
        compare_size = (320, 180)

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    self.stdout.write(self.style.WARNING("Failed to read frame"))
                    time.sleep(options['poll_interval'])
                    continue

                # Resize for comparison
                small = cv2.resize(frame, compare_size)
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

                save_it = False
                if prev_gray is None:
                    save_it = True
                else:
                    diff = cv2.absdiff(gray, prev_gray)
                    mean_diff = diff.mean()
                    if mean_diff >= options['threshold']:
                        save_it = True
                        self.stdout.write(f"Change detected: {mean_diff:.2f}")

                if save_it:
                    # Encode frame to jpg
                    ret, buffer = cv2.imencode('.jpg', frame)
                    if ret:
                        # Save to Django model
                        content = ContentFile(buffer.tobytes())
                        filename = f"sheet{sheet_num}_{side}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                        
                        # Create record
                        CapturedFrame.objects.create(camera=camera, image=ContentFile(buffer.tobytes(), name=filename))
                        
                        prev_gray = gray
                        self.stdout.write(self.style.SUCCESS(f"Saved frame: {filename}"))

                time.sleep(options['poll_interval'])

        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS("Stopping capture"))
        finally:
            cap.release()
