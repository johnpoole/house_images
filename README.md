# House Images Capture & Calibration Toolkit

This repository combines a set of OpenCV utilities for calibrating curling-sheet cameras with a lightweight Django app for managing camera assignments. The tooling lets you:

- Calibrate radial distortion and perspective for a single HDMI capture device.
- Crop the region of interest so only the sheet is processed.
- Continuously monitor the feed and save frames whenever the scene changes.
- Keep a record of cameras/sheets inside a Django dashboard.

## Repository Layout

| Path | Purpose |
| --- | --- |
| `capture_changed_frames.py` | Main capture loop with motion detection, optional rectification/cropping, and HDMI preview controls. |
| `calibration.py` | Click 4 corners in a reference image to build `homography.npy`. |
| `tune_undistort.py`, `undistort_grid.py`, `fit_radial_distortion.py` | Iterative tools to pick/save lens distortion coefficients (`camera_matrix.npy`, `dist_coeffs.npy`, `new_camera_matrix.npy`). |
| `mark_sheet_lines.py` + `compute_crop.py` | Annotate straight lines, fit the crop hull, and persist `crop_rect.npy`. |
| `core/`, `manage.py` | Minimal Django project for tracking sheets, cameras, and captured frames. |
| `requirements.txt` | Python dependencies (OpenCV, NumPy, Django, Pillow). |

Generated artifacts such as `camera_matrix.npy`, `homography.npy`, `crop_rect.npy`, and captured JPEGs live in the repo root, while all reference stills are stored under `jpeg/` alongside their derived previews.

## Prerequisites

- Python 3.11 (the included `.venv` uses 3.11.5).
- HDMI capture device (enumerated by DirectShow on Windows).
- Reference still (`jpeg/sample_sheet.jpg`) that shows the curling sheet clearly.
- For the Django admin, SQLite is configured by default via `db.sqlite3`.

## Environment Setup

```powershell
cd C:\Users\jdpoo\Documents\GitHub\house_images
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If you are on Linux/macOS, drop the `cv2.CAP_DSHOW` flag in scripts that open the camera.

## Calibration Workflow

1. **Pick distortion coefficients**
   - Run `python undistort_grid.py` to generate `jpeg/undistort_grid.jpg` with candidate `k1/k2` values.
   - Use `python tune_undistort.py` for fine-grained sliders, then press `s` to save `camera_matrix.npy`, `dist_coeffs.npy`, `new_camera_matrix.npy`.
   - Alternatively run `mark_sheet_lines.py` to trace straight sheet lines and `fit_radial_distortion.py` to brute-force the best parameters.

2. **Perspective alignment**
   - Open `jpeg/sample_sheet.jpg` in `python calibration.py`, click the four sheet corners in TL→TR→BR→BL order, and close the window to generate `homography.npy` plus `jpeg/warped_preview.jpg`.

3. **Region of interest**
   - After you have an undistorted still, use `python mark_sheet_lines.py` (if you have not already) and `python compute_crop.py` to produce `crop_rect.npy` and `jpeg/undist_cropped.jpg`. The crop rectangle is stored as `[x, y, w, h]` and is applied exactly the same way as in `crop_snippet.py`:
     ```python
     crop_x, crop_y, crop_w, crop_h = np.load("crop_rect.npy")
     roi = undist[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]
     ```

Keep all `.npy` files alongside the capture script so the CLI can find them by default.

## Running the Capture Loop

Basic motion capture with no rectification:

```powershell
.\.venv\Scripts\Activate.ps1
python capture_changed_frames.py --camera-index 1 --no-display
```

Rectified and cropped HDMI preview on a secondary monitor (adjust coordinates to your layout):

```powershell
python capture_changed_frames.py \`
  --camera-index 1 \`
  --rectify \`
  --crop \`
  --fullscreen \`
  --display-x 1920 --display-y 0
```

Key options:

- `--rectify` loads the saved camera matrices and applies undistort + homography before change detection.
- `--crop` applies `crop_rect.npy` either before the homography (when paired with `--rectify`) or as a final ROI.
- `--fullscreen` / `--display-x` / `--display-y` control the OpenCV preview window so you can mirror to an HDMI output.
- `--change-threshold`, `--poll-interval-sec`, etc., can be tweaked in the config section of the script if you need more sensitivity.

Captured frames land in `captured_frames/` and the most recent image is aliased as `captured_frames/latest_frame.jpg` for quick inspection.

## Django Dashboard (optional)

The Django project is minimal but lets you store sheets, cameras, and captured frames.

```powershell
.\.venv\Scripts\Activate.ps1
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Visit `http://localhost:8000/` to reach the dashboard. The views use `core.utils.list_available_cameras` (OpenCV probing) to help assign device indices per sheet side. Calibration and capture buttons trigger management commands so you can drive the workflow without leaving the browser.

### Capture vs. Calibrate

- **Calibrate (`python manage.py calibrate --sheet 1 --camera odd`)**
   1. Grabs a single frame from the selected camera and saves it under `calibration/sheet{sheet}_{side}/calibration_frame_*.jpg` (also updating `captured_frames/latest_frame.jpg`).
   2. Opens an OpenCV window for line marking. Left-click to drop points, press `n` to close a line, `s` to finish, or `Esc` to abort.
   3. Writes the clicks to `line_points_*.json` and stores the payload in a `CalibrationArtifact` record so the dashboard can show the latest calibration metadata.
   4. Marks the `Camera` as calibrated and remembers the folder so other steps can load the `.npy` files you drop in that directory (`camera_matrix.npy`, `dist_coeffs.npy`, `new_camera_matrix.npy`, `homography.npy`, optional `crop_rect.npy`, and optional `rectified_size.json`).

- **Capture (`python manage.py capture --sheet 1 --camera odd`)**
   1. Polls the camera, performing simple frame-diff change detection.
   2. Saves every triggered frame to `captured_frames/` (with a `latest_frame.jpg` alias) and creates a `CapturedFrame` row whose `image` field points to the raw JPEG.
   3. If the camera has a full calibration directory, the command loads those `.npy` files, undistorts/warps the frame, writes the rectified JPEG to `captured_frames/rectified/` (plus `latest_rectified.jpg`), and stores it in the `rectified_image` field.
   4. The sheet detail page now shows both the raw and rectified previews (when available) alongside the metadata from the most recent `CalibrationArtifact`.

## Troubleshooting

- **`Cannot open camera`**: verify the `--camera-index`, unplug/replug the HDMI capture, or close any software already using it.
- **`Crop rectangle extends outside frame bounds`**: re-run `compute_crop.py` after changing rectified dimensions or distortion coefficients.
- **GUI hangs/not responding**: when running on a headless host, pass `--no-display` or configure X forwarding.
- **Different OS**: replace `cv2.CAP_DSHOW` with your platform’s backend (or pass `0` to `VideoCapture`) and adjust the activation commands accordingly.

## Next Steps

- Automate running `capture_changed_frames.py` via a service so it restarts after reboot.
- Wrap calibration scripts into Django management commands for one-click workflows.
- Streamline storage by pointing `captured_frames/` to an external drive or object store when moving to production.
