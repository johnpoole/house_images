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
| `calibration.py` | Legacy helper for hand-clicking sheet corners (auto-calibration now handles this automatically). |
| `tune_undistort.py`, `undistort_grid.py`, `fit_radial_distortion.py` | Legacy tuning utilities if you need to experiment outside the automated pipeline. |
| `mark_sheet_lines.py` + `compute_crop.py` | Legacy scripts for manual line tracing/cropping before the auto pipeline existed. |
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

Camera access now auto-selects the appropriate OpenCV backend (DirectShow on Windows, V4L2 on Linux). You no longer need to edit `cv2.CAP_DSHOW` flags when switching platforms.

## Calibration Workflow

The calibration pipeline is now completely automatic. All you need is a single clean still (no stones, no people) from each camera:

1. **Capture a reference still**
   - From the sheet page, click **Run Auto Calibration**. The view grabs a fresh JPEG from the configured HTTP snapshot source (or the USB device if you still use one) and stores it as a `CapturedFrame`.
   - From the CLI you can run the same logic with `python manage.py calibrate --sheet 1 --camera odd`. Pass `--image path/to/still.jpg` if you already have an artifact.

2. **Auto-detect sheet geometry**
   - The calibration service detects the sheet corners, hog lines, tee lines, back lines, center line, and both houses using World Curling Federation measurements as the reference model.
   - Those features are projected back into the raw camera space, converted into dense polylines, and fed into the undistort/perspective solver.

3. **Review & accept**
   - A pending calibration session appears instantly on the sheet dashboard with raw + rectified previews, fit error, crop rectangle, and a note that auto-detected features were stored.
   - Click **Accept** to publish the artifacts (camera matrix, distortion coefficients, homography, crop rectangle). Click **Reject** to discard and try again if the snapshot was bad.

Legacy scripts such as `tune_undistort.py`, `mark_sheet_lines.py`, and `calibration.py` remain in the repo for debugging, but the standard path is now the fully automatic pipeline above.

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
   1. Captures (or reuses) a still frame for the requested camera and stores it under `calibration/sessions/captures/` so you can audit the input later.
   2. Detects sheet edges, hog lines, tee lines, back lines, the centre line, and both houses without any user interaction.
   3. Runs the full undistort + perspective + crop pipeline, writes the `.npy` artifacts plus preview JPEGs into `calibration/sessions/session_<id>/`, and attaches them to a pending `CalibrationSession` record that the dashboard can review.
   4. Leaves the camera flagged as “calibrated” only after you accept the session from the sheet UI (which copies the staged artifacts into `calibration/sheet{sheet}_{side}/`).

- **Capture (`python manage.py capture --sheet 1 --camera odd`)**
   1. Polls the camera, performing simple frame-diff change detection.
   2. Saves every triggered frame to `captured_frames/` (with a `latest_frame.jpg` alias) and creates a `CapturedFrame` row whose `image` field points to the raw JPEG.
   3. If the camera has a full calibration directory, the command loads those `.npy` files, undistorts/warps the frame, writes the rectified JPEG to `captured_frames/rectified/` (plus `latest_rectified.jpg`), and stores it in the `rectified_image` field.
   4. The sheet detail page now shows both the raw and rectified previews (when available) alongside the metadata from the most recent `CalibrationArtifact`.

   The **Run Auto Calibration** button on the sheet detail page invokes the same flow as `manage.py calibrate`, so you can drive everything from the browser. **Start Motion Capture** fires off the `capture` management command in the background so it can continue saving frames whenever motion is detected, even after the web request returns.
   If a capture session is already running for that camera, the UI automatically switches the button label to **Stop Motion Capture** so you can terminate the stored PID without leaving the dashboard.

### HTTP Snapshot Cameras

Some installations expose each camera as a tiny HTTP server that returns the latest sheet still (e.g., `http://camera-odd.local/latest.jpg`). The Django sheet page now includes a **Snapshot URL** field for each camera card. When you provide a URL, all capture paths (quick still grabs, `manage.py calibrate`, and `manage.py capture`) will fetch frames over HTTP instead of opening a local DirectShow/V4L2 device. Leave the field blank to fall back to a USB/HDMI capture index. You can clear the **Device Index** dropdown to disable local capture entirely when relying on HTTP endpoints.

Use the **Scan Network** button next to the Snapshot URL input to probe the current `/24` subnet for endpoints that respond at `http://<host>:8080/last.jpg`. Any detected hosts are shown as one-click suggestions so you no longer have to type the URLs manually.

## Troubleshooting

- **`Cannot open camera`**: verify the `--camera-index`, unplug/replug the HDMI capture, or close any software already using it.
- **`Crop rectangle extends outside frame bounds`**: re-run `compute_crop.py` after changing rectified dimensions or distortion coefficients.
- **GUI hangs/not responding**: when running on a headless host, pass `--no-display` or configure X forwarding.
- **Different OS**: the app now chooses the capture backend automatically, but you still need the corresponding system drivers (DirectShow on Windows, `v4l2loopback`/`v4l2-ctl` on Linux) and access permissions for the user running Django.

## Next Steps

- Automate running `capture_changed_frames.py` via a service so it restarts after reboot.
- Wrap calibration scripts into Django management commands for one-click workflows.
- Streamline storage by pointing `captured_frames/` to an external drive or object store when moving to production.
