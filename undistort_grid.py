import cv2
import numpy as np

IMAGE_PATH = "sample_sheet.jpg"  # first uploaded distorted image
OUT_PATH   = "undistort_grid.jpg"

img = cv2.imread(IMAGE_PATH)
if img is None:
    raise RuntimeError("Could not read input image")

h, w = img.shape[:2]

# Base camera matrix guess
f = 0.9 * max(w, h)
cx = w / 2.0
cy = h / 2.0
K_base = np.array([[f, 0, cx],
                   [0, f, cy],
                   [0, 0, 1]], dtype=np.float32)

# Candidate (k1, k2) pairs to test
candidates = [
    (-0.15, 0.00),
    (-0.12, 0.01),
    (-0.10, 0.02),   # starting guess
    (-0.08, 0.02),
    (-0.06, 0.02),
    (-0.04, 0.01),
    (-0.02, 0.00),
    ( 0.00, 0.00),   # no distortion (reference)
]

thumbs = []
font = cv2.FONT_HERSHEY_SIMPLEX

for idx, (k1, k2) in enumerate(candidates):
    dist = np.array([k1, k2, 0.0, 0.0, 0.0], dtype=np.float32)
    newK, _ = cv2.getOptimalNewCameraMatrix(K_base, dist, (w, h), 1.0)
    undist = cv2.undistort(img, K_base, dist, None, newK)

    # Make smaller thumbnail for grid
    scale = 0.4
    und_small = cv2.resize(
        undist,
        (int(w * scale), int(h * scale)),
        interpolation=cv2.INTER_AREA
    )

    # Label with index and params
    label = f"{idx}: k1={k1:.2f}, k2={k2:.2f}"
    cv2.putText(und_small, label, (10, 30), font, 0.7, (0, 0, 255), 2)

    thumbs.append(und_small)

# Arrange thumbnails in a grid (2 rows)
cols = 4
rows = int(np.ceil(len(thumbs) / cols))
thumb_h, thumb_w = thumbs[0].shape[:2]
grid = np.zeros((rows * thumb_h, cols * thumb_w, 3), dtype=np.uint8)

for i, t in enumerate(thumbs):
    r = i // cols
    c = i % cols
    grid[r*thumb_h:(r+1)*thumb_h, c*thumb_w:(c+1)*thumb_w] = t

cv2.imwrite(OUT_PATH, grid)
print(f"Saved {OUT_PATH}. Open it and choose the best index.")
