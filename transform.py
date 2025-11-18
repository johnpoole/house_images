import cv2
import numpy as np
import time
from datetime import datetime
import os

# ==== CONFIG ====
DEVICE = 0  # /dev/video0 on Linux, index 0 on Windows
OUT_WIDTH = 800
OUT_HEIGHT = 1600
OUTPUT_DIR = "corrected_frames"
POLL_INTERVAL_SEC = 1.0
CHANGE_THRESHOLD = 5.0
COMPARE_W = 200
COMPARE_H = 400
# ================

os.makedirs(OUTPUT_DIR, exist_ok=True)

H = np.load("homography.npy")

cap = cv2.VideoCapture(DEVICE)
if not cap.isOpened():
    raise RuntimeError("Cannot open capture device")

prev_small = None

def save_frame(frame):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = os.path.join(OUTPUT_DIR, f"frame_{ts}.jpg")
    cv2.imwrite(path, frame)
    print("Saved", path)

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to read frame")
            time.sleep(POLL_INTERVAL_SEC)
            continue

        # Apply perspective correction
        warped = cv2.warpPerspective(frame, H, (OUT_WIDTH, OUT_HEIGHT))

        # Downscale for change detection
        small = cv2.resize(warped, (COMPARE_W, COMPARE_H))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        if prev_small is None:
            save_frame(warped)
            prev_small = gray
        else:
            diff = cv2.absdiff(gray, prev_small)
            mean_diff = diff.mean()

            if mean_diff >= CHANGE_THRESHOLD:
                save_frame(warped)
                prev_small = gray

        time.sleep(POLL_INTERVAL_SEC)

except KeyboardInterrupt:
    pass
finally:
    cap.release()
