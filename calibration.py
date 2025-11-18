import cv2
import numpy as np

# Input image from your capture (distorted)
IMAGE_PATH = "sample_sheet.jpg"

# Output size after correction (tune as needed)
OUT_WIDTH = 800     # horizontal pixels
OUT_HEIGHT = 1600   # vertical pixels

points = []
img = cv2.imread(IMAGE_PATH)
if img is None:
    raise RuntimeError("Could not read image")

img_disp = img.copy()

def mouse_callback(event, x, y, flags, param):
    global points, img_disp
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(points) < 4:
            points.append([x, y])
            cv2.circle(img_disp, (x, y), 6, (0, 0, 255), -1)
            cv2.imshow("Select 4 corners", img_disp)

cv2.namedWindow("Select 4 corners", cv2.WINDOW_NORMAL)
cv2.imshow("Select 4 corners", img_disp)
cv2.setMouseCallback("Select 4 corners", mouse_callback)

print("Click the 4 corners in this order:")
print(" 1) top-left  2) top-right  3) bottom-right  4) bottom-left")
print("Press ESC when done.")

while True:
    key = cv2.waitKey(20) & 0xFF
    if key == 27:  # ESC
        break

cv2.destroyAllWindows()

if len(points) != 4:
    raise RuntimeError(f"Expected 4 points, got {len(points)}")

src = np.array(points, dtype=np.float32)

# Target rectangle
dst = np.array([
    [0, 0],
    [OUT_WIDTH - 1, 0],
    [OUT_WIDTH - 1, OUT_HEIGHT - 1],
    [0, OUT_HEIGHT - 1]
], dtype=np.float32)

# 3x3 homography matrix
H = cv2.getPerspectiveTransform(src, dst)
np.save("homography.npy", H)

# Preview
warped = cv2.warpPerspective(img, H, (OUT_WIDTH, OUT_HEIGHT))
cv2.imwrite("warped_preview.jpg", warped)
print("Saved homography.npy and warped_preview.jpg")
