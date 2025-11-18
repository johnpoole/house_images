import cv2
import json

IMAGE_PATH = "sample_sheet.jpg"   # raw distorted frame
OUT_JSON   = "sheet_lines.json"

img = cv2.imread(IMAGE_PATH)
if img is None:
    raise RuntimeError("Could not read image")

lines = []          # list of lines; each line = list of (x, y)
current_line = []   # points for the line you're drawing now

display = img.copy()
win = "mark_lines"
cv2.namedWindow(win, cv2.WINDOW_NORMAL)

def mouse_cb(event, x, y, flags, param):
    global current_line, display
    if event == cv2.EVENT_LBUTTONDOWN:
        current_line.append((int(x), int(y)))
        cv2.circle(display, (x, y), 4, (0, 0, 255), -1)
        cv2.imshow(win, display)

cv2.setMouseCallback(win, mouse_cb)

print("Instructions:")
print(" - Click several points along the HOG line (left to right),")
print("   then press 'n' to finish that line.")
print(" - Repeat for TEE line and END line (or any other straight lines).")
print(" - Press 's' when all lines are done to save.")
print(" - Press ESC to abort.")

cv2.imshow(win, display)

while True:
    key = cv2.waitKey(20) & 0xFF
    if key == 27:  # ESC
        lines = []
        break
    elif key == ord('n'):
        if current_line:
            lines.append(current_line)
            current_line = []
            print(f"Line {len(lines)} stored.")
    elif key == ord('s'):
        if current_line:
            lines.append(current_line)
            current_line = []
        if lines:
            break

cv2.destroyAllWindows()

if not lines:
    print("No lines saved.")
else:
    data = {"lines": lines}
    with open(OUT_JSON, "w") as f:
        json.dump(data, f)
    print(f"Saved {len(lines)} lines to {OUT_JSON}")
