import cv2
import json
import numpy as np

IMG_PATH      = "undist_best.jpg"
LINES_JSON    = "sheet_lines.json"
K_PATH        = "camera_matrix.npy"
DIST_PATH     = "dist_coeffs.npy"
NEWK_PATH     = "new_camera_matrix.npy"
CROP_OUT_IMG  = "undist_cropped.jpg"
CROP_RECT_NPY = "crop_rect.npy"      # [x, y, w, h]

# Load data
img   = cv2.imread(IMG_PATH)
if img is None:
    raise RuntimeError("Could not read undistorted image")

h, w = img.shape[:2]

with open(LINES_JSON, "r") as f:
    data = json.load(f)

lines = [np.array(l, dtype=np.float32) for l in data["lines"]]

K    = np.load(K_PATH)
dist = np.load(DIST_PATH)
newK = np.load(NEWK_PATH)

# Undistort the clicked points into the same coordinate system as undist_best.jpg
all_pts = []
for pts in lines:
    pts = pts.reshape(-1, 1, 2)
    und = cv2.undistortPoints(pts, K, dist, P=newK)  # P=newK -> pixel coords in undistorted image
    und = und.reshape(-1, 2)
    all_pts.append(und)

all_pts = np.vstack(all_pts).astype(np.float32)

# Use convex hull of all undistorted points, then its bounding rectangle
hull = cv2.convexHull(all_pts)
x, y, cw, ch = cv2.boundingRect(hull)

# Crop
crop = img[y:y+ch, x:x+cw]
cv2.imwrite(CROP_OUT_IMG, crop)

# Save the rectangle for later use on live frames
np.save(CROP_RECT_NPY, np.array([x, y, cw, ch], dtype=np.int32))

print("Crop rect:", x, y, cw, ch)
print("Saved", CROP_OUT_IMG, "and", CROP_RECT_NPY)
