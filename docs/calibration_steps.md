# Calibration Steps (Django Flow)

These instructions describe how to perform calibration entirely inside the Django app. Every artifact is captured, stored, and applied by the web workflow—no helper scripts or JSON shuffling required.

## 0. Prerequisites

- Cameras online and visible in the Django UI (`/sheets/<id>/`).
- Staff account with permission to click the **Calibrate** button on the sheet detail page.
- Window manager access to the host so the OpenCV preview created by Django is visible (the browser launches the worker but the clicks happen in the OS window).

## 1. Launch Calibration

- Navigate to the sheet in Django and click **Calibrate** next to the camera you want to tune.
- The server captures a still frame, stores it in SQLite, and opens the interactive window on the host running the Django process.
- The Django task is now waiting for input; do not close the browser tab until the workflow finishes.

## 2. Trace the Sheet Lines

- Click along each of the three long lines on the sheet (far hog, center/tee, near hog) in order.
- Press `n` when you finish each line; the UI clears the overlay so you can start tracing the next one.
- After all three lines look good, press `s`. Django writes every click into the SQLite database (`CalibrationLinePoint` rows linked to the sheet/camera), so there is no JSON export.
- Close the window if prompted; Django now has everything it needs to solve for distortion.

## 3. Review Stored Data

- Back in the browser, the sheet detail page shows the timestamp of the new calibration attempt and exposes the recorded click counts.
- If you mis-clicked or skipped a line, restart by hitting **Calibrate** again; Django overwrites the previous points for that camera.

## 4. Fit Distortion, Crop, and Approve

- As soon as you submit the points, Django runs `fit_radial_distortion` and the cropper on the captured still.
- The browser shows a before/after pair: undistorted frame plus the cropped/rectified preview that will be used during motion capture.
- Choose **Accept** to keep the result. Django stores the camera matrix, distortion coefficients, homography, and crop rectangle inside SQLite and writes the same data to the calibration artifact directory. Rejecting drops the artifacts and leaves the camera uncalibrated.
- Acceptance flips the camera to calibrated status; any future motion-capture sessions automatically undistort and crop every frame before persisting it. Each `CapturedFrame` now has both `image` (raw JPEG) and `rectified_image` (corrected JPEG) on disk and in Django’s media records.

## 5. Verify Motion Capture

- Start a short capture from the Django UI (or `python manage.py capture --sheet ... --camera ... --max-frames 1`).
- Confirm that the live preview and saved frames use the corrected geometry. The sheet lines in the rectified image should be parallel and the ROI should match the expected house area.
- If something looks off, redo the calibration: click **Calibrate**, re-trace, and either accept the new preview or keep iterating until satisfied.

## 6. Document Context

- Use the `CalibrationArtifact.notes` field (Django admin) to record anything unusual: camera moved, lighting changed, crop manually tweaked, etc.
- Good notes make it clear why rectified frames taken after this calibration might differ from earlier sessions and help when reprocessing historical motion events.
