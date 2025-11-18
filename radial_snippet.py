import cv2
import numpy as np

K    = np.load("camera_matrix.npy")
dist = np.load("dist_coeffs.npy")
newK = np.load("new_camera_matrix.npy")

# Assume you already have homography H from your earlier step
H = np.load("homography.npy")

OUT_WIDTH  = 800   # or whatever you chose
OUT_HEIGHT = 1600

cap = cv2.VideoCapture(0)  # or "/dev/video0"

while True:
    ret, frame = cap.read()
    if not ret:
        break

    undist = cv2.undistort(frame, K, dist, None, newK)
    corrected = cv2.warpPerspective(undist, H, (OUT_WIDTH, OUT_HEIGHT))

    # show, save, or diff against previous frame
    cv2.imshow("corrected", corrected)
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()
