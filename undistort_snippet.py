import cv2
import numpy as np

K    = np.load("camera_matrix.npy")
dist = np.load("dist_coeffs.npy")
newK = np.load("new_camera_matrix.npy")

cap = cv2.VideoCapture(0)  # or "/dev/video0"

while True:
    ret, frame = cap.read()
    if not ret:
        break

    undist = cv2.undistort(frame, K, dist, None, newK)

    cv2.imshow("undistorted", undist)
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()
