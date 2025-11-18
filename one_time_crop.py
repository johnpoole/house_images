import cv2
import json
import numpy as np

IMG_PATH      = "undist_best.jpg"
LINES_JSON    = "sheet_lines.json"
K_PATH        = "camera_matrix.npy"
DIST_PATH     = "dist_coeffs.npy"
NEWK_PATH     = "new_camera_matrix.npy"
CROP_OUT_IMG  = "undist_cropped.jpg"
CROP_RECT_NPY = "crop_rect.npy"   # [x, y, w, h]

MARGIN = 4  # pixels to move inside each boundary

# Load undistorted image
img = cv2.imread(IMG_PATH)
if img is None:
    raise RuntimeError("Could not read undistorted image")
h, w = img.shape[:2]

# Load lines (clicked in distorted image)
with open(LINES_JSON, "r") as f:
    data = json.load(f)
lines_raw = [np.array(l, dtype=np.float32) for l in data["lines"]]
if len(lines_raw) < 2:
    raise RuntimeError("Need at least 2 lines")

# Load camera params
K    = np.load(K_PATH)
dist = np.load(DIST_PATH)
newK = np.load(NEWK_PATH)

line_info = []  # list of (y_mean, x_left, x_right)

for pts in lines_raw:
    if pts.shape[0] < 2:
        continue

    # take first and last point only
    endpoints = np.vstack([pts[0], pts[-1]]).reshape(-1, 1, 2)

    # undistort endpoints into pixel coords of undistorted image
    und = cv2.undistortPoints(endpoints, K, dist, P=newK).reshape(-1, 2)

    x0, y0 = und[0]
    x1, y1 = und[1]

    x_left_line  = min(x0, x1)
    x_right_line = max(x0, x1)
    y_mean       = 0.5 * (y0 + y1)

    line_info.append((y_mean, x_left_line, x_right_line))

if len(line_info) < 2:
    raise RuntimeError("Not enough valid lines after processing")

# Horizontal limits: intersection of all line segments
x_left  = max(li[1] for li in line_info) + MARGIN
x_right = min(li[2] for li in line_info) - MARGIN

# Vertical limits: outermost lines
line_info.sort(key=lambda t: t[0])  # sort by y_mean
y_top = line_info[0][0] + MARGIN          # just below top line
y_bot = line_info[-1][0] - MARGIN         # just above bottom line

# Clamp and convert to ints
x_left  = int(max(0, min(w-1, x_left)))
x_right = int(max(0, min(w-1, x_right)))
y_top   = int(max(0, min(h-1, y_top)))
y_bot   = int(max(0, min(h-1, y_bot)))

if x_right <= x_left or y_bot <= y_top:
    raise RuntimeError(f"Invalid crop box: ({x_left},{y_top})–({x_right},{y_bot})")

cw = x_right - x_left
ch = y_bot - y_top

crop = img[y_top:y_top+ch, x_left:x_left+cw]
cv2.imwrite(CROP_OUT_IMG, crop)
np.save(CROP_RECT_NPY, np.array([x_left, y_top, cw, ch], dtype=np.int32))

print("Crop rect:", x_left, y_top, cw, ch)
print("Saved", CROP_OUT_IMG, "and", CROP_RECT_NPY)
