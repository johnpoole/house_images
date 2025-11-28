import json
import os
import re
import shutil
import subprocess

import cv2


def _preferred_capture_api():
    if os.name == 'nt' and hasattr(cv2, 'CAP_DSHOW'):
        return cv2.CAP_DSHOW  # type: ignore[attr-defined]
    if os.name == 'posix' and hasattr(cv2, 'CAP_V4L2'):
        return cv2.CAP_V4L2  # type: ignore[attr-defined]
    return None


def open_camera(index):
    api = _preferred_capture_api()
    if api is not None:
        cap = cv2.VideoCapture(index, api)
        if cap.isOpened():
            return cap
        cap.release()
    return cv2.VideoCapture(index)


def list_available_cameras(max_range=10):
    """Return indices for cameras that successfully deliver a frame."""
    available = []
    for i in range(max_range):
        cap = open_camera(i)
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


def _linux_camera_friendly_names():
    if os.name != 'posix' or shutil.which('v4l2-ctl') is None:
        return {}
    try:
        result = subprocess.run(
            ['v4l2-ctl', '--list-devices'],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return {}
    mapping = {}
    current_name = None
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        if not line.startswith('\t'):
            current_name = line.strip().rstrip(':')
            continue
        match = re.search(r'/dev/video(\d+)', line)
        if match and current_name:
            mapping[int(match.group(1))] = current_name
    return mapping


def labeled_camera_choices(max_range=10):
    """Return camera indices paired with user-friendly labels when possible."""
    indices = list_available_cameras(max_range=max_range)
    if os.name == 'nt':
        names = _windows_camera_friendly_names()
        lookup = {idx: name for idx, name in zip(indices, names)}
    else:
        lookup = _linux_camera_friendly_names()
    choices = []
    for idx in indices:
        friendly = lookup.get(idx)
        label = f"{friendly} (Device {idx})" if friendly else f"Device {idx}"
        choices.append({'index': idx, 'label': label})
    return choices
