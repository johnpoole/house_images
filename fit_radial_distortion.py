import os
import cv2
import json
import numpy as np

JPEG_DIR = "jpeg"

IMAGE_PATH = os.path.join(JPEG_DIR, "sample_sheet.jpg")
LINES_JSON = "sheet_lines.json"

CAMERA_MATRIX_OUT = "camera_matrix.npy"
DIST_COEFFS_OUT   = "dist_coeffs.npy"
NEW_CAMERA_OUT    = "new_camera_matrix.npy"
UNDIST_PREVIEW    = os.path.join(JPEG_DIR, "undist_best.jpg")

with open(LINES_JSON, "r") as f:
    data = json.load(f)

lines = data["lines"]  # list of list of [x, y]
lines = [np.array(l, dtype=np.float32) for l in lines]

img = cv2.imread(IMAGE_PATH)
if img is None:
    raise RuntimeError("Could not read image")

h, w = img.shape[:2]
base = float(max(w, h))

def line_rms(pts):
    """
    pts: Nx2 array
    returns RMS distance from best-fit line
    """
    if pts.shape[0] < 2:
        return 0.0
    mean = pts.mean(axis=0)
    centered = pts - mean
    # PCA via SVD
    _, s, vt = np.linalg.svd(centered)
    # second singular vector is orthogonal direction
    orth = vt[1]
    d = centered @ orth
    return float(np.sqrt((d * d).mean()))

def eval_params(f_factor, k1, k2):
    f = f_factor * base
    cx = w / 2.0
    cy = h / 2.0
    K = np.array([[f, 0, cx],
                  [0, f, cy],
                  [0, 0, 1]], dtype=np.float32)
    dist = np.array([k1, k2, 0.0, 0.0, 0.0], dtype=np.float32)

    total = 0.0
    for pts in lines:
        # undistort points, keeping them in pixel coords using P=K
        pts_reshaped = pts.reshape(-1, 1, 2)
        und = cv2.undistortPoints(pts_reshaped, K, dist, P=K)
        und = und.reshape(-1, 2)
        total += line_rms(und)
    return total, K, dist

# Search grid (adjust if needed)
f_factors = [0.7, 0.8, 0.9, 1.0, 1.1]
k1_vals   = [-0.30, -0.20, -0.15, -0.10, -0.05, 0.0]
k2_vals   = [-0.10, -0.05, 0.0, 0.05]

best_err = None
best_K = None
best_dist = None
best_combo = None

for f_factor in f_factors:
    for k1 in k1_vals:
        for k2 in k2_vals:
            err, K, dist = eval_params(f_factor, k1, k2)
            if best_err is None or err < best_err:
                best_err = err
                best_K = K
                best_dist = dist
                best_combo = (f_factor, k1, k2)
                print(f"New best: f_factor={f_factor}, k1={k1}, k2={k2}, err={err:.4f}")

print("Best combo:", best_combo, "err=", best_err)

# Compute a 'new camera matrix' for full image undistortion
newK, _ = cv2.getOptimalNewCameraMatrix(best_K, best_dist, (w, h), 1.0)

np.save(CAMERA_MATRIX_OUT, best_K)
np.save(DIST_COEFFS_OUT, best_dist)
np.save(NEW_CAMERA_OUT, newK)

undist = cv2.undistort(img, best_K, best_dist, None, newK)
os.makedirs(JPEG_DIR, exist_ok=True)
cv2.imwrite(UNDIST_PREVIEW, undist)
print("Saved:")
print(" ", CAMERA_MATRIX_OUT)
print(" ", DIST_COEFFS_OUT)
print(" ", NEW_CAMERA_OUT)
print(" ", UNDIST_PREVIEW)
