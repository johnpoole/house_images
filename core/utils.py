import json
import os
import subprocess

import cv2


def list_available_cameras(max_range=10):
    """Return indices for cameras that successfully deliver a frame."""
    available = []
    for i in range(max_range):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)  # type: ignore[attr-defined]
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                available.append(i)
            cap.release()
    return available


def _windows_camera_friendly_names():
    """Best-effort fetch of Windows camera device names via PowerShell."""
    if os.name != 'nt':
        return []
    script = (
        "Get-PnpDevice -Class Camera | Select-Object -ExpandProperty FriendlyName | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', script],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = result.stdout.strip()
        if not payload:
            return []
        data = json.loads(payload)
        if isinstance(data, str):
            return [data]
        if isinstance(data, list):
            return [name for name in data if isinstance(name, str) and name.strip()]
    except (subprocess.CalledProcessError, json.JSONDecodeError, OSError):
        pass
    return []


def labeled_camera_choices(max_range=10):
    """Return camera indices paired with user-friendly labels when possible."""
    indices = list_available_cameras(max_range=max_range)
    friendly_names = _windows_camera_friendly_names()
    choices = []
    friendly_iter = iter(friendly_names)
    for idx in indices:
        friendly = next(friendly_iter, None)
        if friendly:
            label = f"{friendly} (Device {idx})"
        else:
            label = f"Device {idx}"
        choices.append({'index': idx, 'label': label})
    return choices
