import os
import cv2
import numpy as np

JPEG_DIR = "jpeg"
IMAGE_PATH = os.path.join(JPEG_DIR, "sample_sheet.jpg")   # your distorted image

img = cv2.imread(IMAGE_PATH)
if img is None:
    raise RuntimeError("Could not read image")

h, w = img.shape[:2]

# --- Initial camera matrix guess ---
# Assume square pixels, principal point at image center
f = 0.9 * max(w, h)   # focal length guess; you can change 0.9
cx = w / 2.0
cy = h / 2.0

K = np.array([[f, 0, cx],
              [0, f, cy],
              [0, 0,   1]], dtype=np.float32)

# Trackbar ranges: slider 0..1000 => value in approx [-0.5, 0.5]
def slider_to_k(v):
    return (v - 500) / 1000.0

cv2.namedWindow("undistort", cv2.WINDOW_NORMAL)

# Create trackbars
cv2.createTrackbar("k1", "undistort", 500, 1000, lambda x: None)
cv2.createTrackbar("k2", "undistort", 500, 1000, lambda x: None)
# Optional higher-order terms if needed:
# cv2.createTrackbar("k3", "undistort", 500, 1000, lambda x: None)

print("Use sliders k1, k2 to straighten lines / circles.")
print("Press 's' to save parameters, ESC to exit without saving.")

saved = False
best_params = None

while True:
    k1 = slider_to_k(cv2.getTrackbarPos("k1", "undistort"))
    k2 = slider_to_k(cv2.getTrackbarPos("k2", "undistort"))
    # k3 = slider_to_k(cv2.getTrackbarPos("k3", "undistort"))

    dist = np.array([k1, k2, 0.0, 0.0, 0.0], dtype=np.float32)

    # Compute optimal new camera matrix (keeps FOV)
    newK, _ = cv2.getOptimalNewCameraMatrix(K, dist, (w, h), 1.0)

    undist = cv2.undistort(img, K, dist, None, newK)

    # Show side-by-side for reference
    vis = np.hstack([img, undist])
    cv2.imshow("undistort", vis)

    key = cv2.waitKey(30) & 0xFF
    if key == 27:  # ESC
        break
    elif key == ord('s'):
        best_params = (K, dist, newK)
        np.save("camera_matrix.npy", K)
        np.save("dist_coeffs.npy", dist)
        np.save("new_camera_matrix.npy", newK)
        print("Saved camera_matrix.npy, dist_coeffs.npy, new_camera_matrix.npy")
        saved = True

cv2.destroyAllWindows()

if not saved:
    print("Parameters not saved (ESC pressed).")
