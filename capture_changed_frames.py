import argparse
import cv2
import numpy as np
import os
import sys
import time
from datetime import datetime
from typing import Optional, Tuple

# ==== CONFIG ====
DEFAULT_CAMERA_INDEX = 0  # Change to 1, 2, ... if your HDMI-USB device isn't at 0
OUTPUT_DIR = "captured_frames"
LATEST_FRAME_ALIAS = "latest_frame.jpg"
POLL_INTERVAL_SEC = 1.0   # How often to poll (seconds)
CHANGE_THRESHOLD = 5.0    # Mean pixel difference threshold (tune as needed)
COMPARE_WIDTH = 320       # Downscaled width for comparison
COMPARE_HEIGHT = 180      # Downscaled height for comparison
WINDOW_NAME = "Latest captured frame"
DEFAULT_CAMERA_MATRIX = "camera_matrix.npy"
DEFAULT_DIST_COEFFS = "dist_coeffs.npy"
DEFAULT_NEW_CAMERA_MATRIX = "new_camera_matrix.npy"
DEFAULT_HOMOGRAPHY = "homography.npy"
DEFAULT_RECTIFIED_WIDTH = 800
DEFAULT_RECTIFIED_HEIGHT = 1600
DEFAULT_CROP_RECT = "crop_rect.npy"
# =================

def save_frame(frame):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = os.path.join(OUTPUT_DIR, f"frame_{ts}.jpg")
    cv2.imwrite(filename, frame)
    # Keep an easy-to-find alias for the latest capture so it can be shown elsewhere.
    latest_path = os.path.join(OUTPUT_DIR, LATEST_FRAME_ALIAS)
    cv2.imwrite(latest_path, frame)
    print(f"Saved: {filename} (latest -> {latest_path})")
    return filename

class FrameDisplay:
    """Encapsulates the OpenCV window so we can toggle fullscreen/move windows."""

    def __init__(
        self,
        enabled: bool,
        fullscreen: bool = False,
        position: Optional[Tuple[int, int]] = None,
        size: Optional[Tuple[int, int]] = None,
    ) -> None:
        self.enabled = enabled
        if not enabled:
            return

        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        if size and size[0] > 0 and size[1] > 0:
            cv2.resizeWindow(WINDOW_NAME, size[0], size[1])
        if position:
            cv2.moveWindow(WINDOW_NAME, position[0], position[1])
        if fullscreen:
            cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    def show(self, frame):
        if not self.enabled:
            return
        cv2.imshow(WINDOW_NAME, frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):  # Allow quick exit via Q or ESC
            raise KeyboardInterrupt

    def close(self):
        if self.enabled:
            cv2.destroyWindow(WINDOW_NAME)


class FrameCropper:
    """Slices frames using a rect stored in crop_rect.npy (x, y, w, h)."""

    def __init__(self, crop_rect_path: str) -> None:
        rect = np.load(crop_rect_path)
        if rect.shape != (4,) and rect.shape != (1, 4):
            raise ValueError(
                f"Crop rect in {crop_rect_path} must be [x, y, w, h]; got shape {rect.shape}"
            )
        rect = rect.reshape(-1)
        self.x, self.y, self.w, self.h = [int(v) for v in rect]

    def __call__(self, frame):
        y2 = self.y + self.h
        x2 = self.x + self.w
        if self.x < 0 or self.y < 0 or y2 > frame.shape[0] or x2 > frame.shape[1]:
            raise ValueError(
                "Crop rectangle extends outside frame bounds; "
                "update crop_rect.npy or disable --crop"
            )
        return frame[self.y:y2, self.x:x2]


class FrameRectifier:
    """Applies undistort + (optional crop) + perspective warp."""

    def __init__(
        self,
        camera_matrix_path: str,
        dist_coeffs_path: str,
        new_camera_matrix_path: str,
        homography_path: str,
        out_width: int,
        out_height: int,
        cropper: Optional[FrameCropper] = None,
    ) -> None:
        self.K = np.load(camera_matrix_path)
        self.dist = np.load(dist_coeffs_path)
        self.newK = np.load(new_camera_matrix_path)
        self.H = np.load(homography_path)
        self.out_size = (int(out_width), int(out_height))
        self.cropper = cropper

    def __call__(self, frame):
        undist = cv2.undistort(frame, self.K, self.dist, None, self.newK)
        if self.cropper:
            undist = self.cropper(undist)
        return cv2.warpPerspective(undist, self.H, self.out_size)

def list_available_cameras(max_index: int) -> None:
    print("Probing camera indexes 0..{}".format(max_index))
    found_any = False
    for idx in range(max_index + 1):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        try:
            if cap.isOpened():
                print(f"  Index {idx}: AVAILABLE")
                found_any = True
            else:
                print(f"  Index {idx}: not available")
        finally:
            cap.release()
    if not found_any:
        print("No cameras responded in that range.")

def parse_args():
    parser = argparse.ArgumentParser(description="Capture frames when scene changes")
    parser.add_argument(
        "--camera-index",
        "-c",
        type=int,
        default=DEFAULT_CAMERA_INDEX,
        help="Camera index to open (default: %(default)s)",
    )
    parser.add_argument(
        "--list-cameras",
        action="store_true",
        help="List camera statuses (0..probe-range) and exit",
    )
    parser.add_argument(
        "--probe-range",
        type=int,
        default=3,
        help="Highest index to probe when using --list-cameras",
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Disable the preview window that shows the last captured frame",
    )
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="Show the preview window in fullscreen (useful for HDMI displays)",
    )
    parser.add_argument(
        "--display-x",
        type=int,
        help="Move the preview window to this X coordinate (set to secondary monitor offset)",
    )
    parser.add_argument(
        "--display-y",
        type=int,
        help="Move the preview window to this Y coordinate",
    )
    parser.add_argument(
        "--display-width",
        type=int,
        help="Resize the preview window to this width (ignored when --fullscreen is used)",
    )
    parser.add_argument(
        "--display-height",
        type=int,
        help="Resize the preview window to this height (ignored when --fullscreen is used)",
    )
    parser.add_argument(
        "--rectify",
        action="store_true",
        help="Undistort + warp frames using calibration data (radial_snippet integration)",
    )
    parser.add_argument(
        "--camera-matrix-path",
        default=DEFAULT_CAMERA_MATRIX,
        help="Path to camera_matrix.npy (used with --rectify)",
    )
    parser.add_argument(
        "--dist-coeffs-path",
        default=DEFAULT_DIST_COEFFS,
        help="Path to dist_coeffs.npy (used with --rectify)",
    )
    parser.add_argument(
        "--new-camera-matrix-path",
        default=DEFAULT_NEW_CAMERA_MATRIX,
        help="Path to new_camera_matrix.npy (used with --rectify)",
    )
    parser.add_argument(
        "--homography-path",
        default=DEFAULT_HOMOGRAPHY,
        help="Path to homography.npy (used with --rectify)",
    )
    parser.add_argument(
        "--rectified-width",
        type=int,
        default=DEFAULT_RECTIFIED_WIDTH,
        help="Width of the warped output frame when --rectify is enabled",
    )
    parser.add_argument(
        "--rectified-height",
        type=int,
        default=DEFAULT_RECTIFIED_HEIGHT,
        help="Height of the warped output frame when --rectify is enabled",
    )
    parser.add_argument(
        "--crop",
        action="store_true",
        help="Apply the crop defined in crop_rect.npy (after rectification if enabled)",
    )
    parser.add_argument(
        "--crop-rect-path",
        default=DEFAULT_CROP_RECT,
        help="Path to crop_rect.npy storing [x, y, w, h] (used with --crop)",
    )
    return parser.parse_args()

def main():
    args = parse_args()

    if args.list_cameras:
        list_available_cameras(args.probe_range)
        sys.exit(0)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    cap = cv2.VideoCapture(args.camera_index, cv2.CAP_DSHOW)  # CAP_DSHOW is good for Windows; omit on Linux

    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera at index {args.camera_index}")

    prev_gray_small = None
    display_enabled = not args.no_display
    display_position = None
    if args.display_x is not None and args.display_y is not None:
        display_position = (args.display_x, args.display_y)
    display_size = None
    if args.display_width is not None and args.display_height is not None:
        display_size = (args.display_width, args.display_height)
    frame_display = FrameDisplay(
        enabled=display_enabled,
        fullscreen=args.fullscreen,
        position=display_position,
        size=None if args.fullscreen else display_size,
    )

    cropper: Optional[FrameCropper] = None
    if args.crop:
        if not os.path.exists(args.crop_rect_path):
            raise FileNotFoundError(
                f"Cannot enable --crop; missing rectangle file {args.crop_rect_path}"
            )
        cropper = FrameCropper(args.crop_rect_path)

    rectifier: Optional[FrameRectifier] = None
    post_rect_cropper = cropper
    if args.rectify:
        missing = [
            path
            for path in (
                args.camera_matrix_path,
                args.dist_coeffs_path,
                args.new_camera_matrix_path,
                args.homography_path,
            )
            if not os.path.exists(path)
        ]
        if missing:
            missing_str = ", ".join(missing)
            raise FileNotFoundError(f"Cannot enable --rectify; missing files: {missing_str}")
        rectifier = FrameRectifier(
            camera_matrix_path=args.camera_matrix_path,
            dist_coeffs_path=args.dist_coeffs_path,
            new_camera_matrix_path=args.new_camera_matrix_path,
            homography_path=args.homography_path,
            out_width=args.rectified_width,
            out_height=args.rectified_height,
            cropper=cropper,
        )
        post_rect_cropper = None

    try:
        while True:
            ret, raw_frame = cap.read()
            if not ret:
                print("Warning: failed to read frame from capture device")
                time.sleep(POLL_INTERVAL_SEC)
                continue

            frame = rectifier(raw_frame) if rectifier else raw_frame
            frame = post_rect_cropper(frame) if post_rect_cropper else frame

            frame_small = cv2.resize(frame, (COMPARE_WIDTH, COMPARE_HEIGHT))
            gray_small = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)

            if prev_gray_small is None:
                save_frame(frame)
                frame_display.show(frame)
                prev_gray_small = gray_small
            else:
                diff = cv2.absdiff(gray_small, prev_gray_small)
                mean_diff = diff.mean()

                if mean_diff >= CHANGE_THRESHOLD:
                    save_frame(frame)
                    frame_display.show(frame)
                    prev_gray_small = gray_small

            time.sleep(POLL_INTERVAL_SEC)

    except KeyboardInterrupt:
        print("Stopping capture.")

    finally:
        cap.release()
        frame_display.close()


if __name__ == "__main__":
    main()
