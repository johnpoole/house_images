import numpy as np
import cv2

# Load once at startup
crop_x, crop_y, crop_w, crop_h = np.load("crop_rect.npy")

# inside your capture loop, after undistortion:
# undist = cv2.undistort(frame, K, dist, None, newK)

roi = undist[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]
# now use `roi` (display, save, feed to homography, etc.)
