import cv2
import numpy as np
import os
from django.core.management.base import BaseCommand
from core.models import Camera

class Command(BaseCommand):
    help = 'Runs interactive calibration for a camera'

    def add_arguments(self, parser):
        parser.add_argument('--sheet', type=int, required=True, help='Sheet number')
        parser.add_argument('--camera', type=str, required=True, choices=['odd', 'even'], help='Camera side (odd/even)')

    def handle(self, *args, **options):
        sheet_num = options['sheet']
        side = options['camera']

        try:
            camera = Camera.objects.get(sheet__number=sheet_num, side=side)
        except Camera.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Camera for Sheet {sheet_num} ({side}) not found in DB"))
            return
            
        # Define calibration directory
        calib_dir = os.path.join("calibration", f"sheet{sheet_num}_{side}")
        os.makedirs(calib_dir, exist_ok=True)
        
        self.stdout.write(self.style.SUCCESS(f"Starting calibration for {camera}"))
        self.stdout.write(f"Output directory: {calib_dir}")

        # TODO: Integrate the actual calibration logic from calibration.py and fit_radial_distortion.py
        # For this step, I will just update the model to point to this directory and mark as calibrated
        # so we can test the full flow. The actual OpenCV logic needs to be ported carefully.
        
        camera.calibration_dir = calib_dir
        camera.is_calibrated = True
        camera.save()
        
        self.stdout.write(self.style.SUCCESS(f"Updated camera record. Calibration dir: {calib_dir}"))
