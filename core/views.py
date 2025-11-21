import os
import signal
import subprocess
import sys

from django.conf import settings
from django.db.models import Prefetch
from django.shortcuts import render, redirect, get_object_or_404
from django.core.management import call_command
from django.contrib import messages
from .models import Sheet, Camera, CapturedFrame, CalibrationArtifact
from .utils import list_available_cameras

def dashboard(request):
    sheets = Sheet.objects.all().order_by('number')
    return render(request, 'core/dashboard.html', {'sheets': sheets})

def sheet_detail(request, sheet_id):
    sheet = get_object_or_404(Sheet, number=sheet_id)

    available_indices = list_available_cameras(max_range=4)

    frame_prefetch = Prefetch(
        'frames',
        queryset=CapturedFrame.objects.order_by('-timestamp'),
        to_attr='prefetched_frames'
    )
    artifact_prefetch = Prefetch(
        'calibration_artifacts',
        queryset=CalibrationArtifact.objects.order_by('-created_at'),
        to_attr='prefetched_artifacts'
    )

    camera_cards = []
    cameras = Camera.objects.filter(sheet=sheet).prefetch_related(frame_prefetch, artifact_prefetch)
    for cam in cameras:
        last_frame = cam.prefetched_frames[0] if cam.prefetched_frames else None
        last_artifact = cam.prefetched_artifacts[0] if cam.prefetched_artifacts else None
        camera_cards.append({
            'camera': cam,
            'last_frame': last_frame,
            'last_artifact': last_artifact,
        })

    return render(request, 'core/sheet_detail.html', {
        'sheet': sheet,
        'available_indices': available_indices,
        'camera_cards': camera_cards,
    })

def update_camera(request):
    if request.method == 'POST':
        sheet_num = request.POST.get('sheet_id')
        side = request.POST.get('side')
        new_index = request.POST.get('device_index')
        
        try:
            camera = Camera.objects.get(sheet__number=sheet_num, side=side)
            camera.device_index = int(new_index)
            camera.save()
            messages.success(request, f"Updated {side} camera to Device {new_index}")
        except Exception as e:
            messages.error(request, f"Error updating camera: {str(e)}")
            
        return redirect('sheet_detail', sheet_id=sheet_num)
    return redirect('dashboard')

def trigger_calibrate(request):
    if request.method == 'POST':
        sheet_num = request.POST.get('sheet_id')
        side = request.POST.get('side')
        next_url = request.POST.get('next', 'dashboard')
        try:
            call_command('calibrate', sheet=int(sheet_num), camera=side)
            messages.success(request, f"Calibration finished for Sheet {sheet_num} {side}")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
        return redirect(next_url)
    return redirect('dashboard')

def trigger_motion_capture(request):
    if request.method == 'POST':
        sheet_num = request.POST.get('sheet_id')
        side = request.POST.get('side')
        next_url = request.POST.get('next', 'dashboard')

        try:
            sheet_num_int = int(sheet_num)
        except (TypeError, ValueError):
            messages.error(request, "Invalid sheet number supplied for motion capture.")
            return redirect(next_url)

        camera = get_object_or_404(Camera, sheet__number=sheet_num_int, side=side)
        if camera.motion_capture_pid:
            messages.warning(request, "Motion capture already appears to be running. Stop it before starting a new session.")
            return redirect(next_url)

        manage_py = os.path.join(settings.BASE_DIR, 'manage.py')
        cmd = [sys.executable, manage_py, 'capture', '--sheet', str(sheet_num_int), '--camera', side]

        creationflags = 0
        if os.name == 'nt':
            creationflags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)

        try:
            proc = subprocess.Popen(cmd, cwd=settings.BASE_DIR, creationflags=creationflags)
            camera.motion_capture_pid = proc.pid
            camera.save(update_fields=['motion_capture_pid'])
            messages.success(request, f"Started motion capture for Sheet {sheet_num} {side}. Use Stop to end it.")
        except Exception as exc:
            messages.error(request, f"Failed to launch motion capture: {exc}")
        return redirect(next_url)
    return redirect('dashboard')


def stop_motion_capture(request):
    if request.method == 'POST':
        sheet_num = request.POST.get('sheet_id')
        side = request.POST.get('side')
        next_url = request.POST.get('next', 'dashboard')

        try:
            sheet_num_int = int(sheet_num)
        except (TypeError, ValueError):
            messages.error(request, "Invalid sheet number supplied for stopping motion capture.")
            return redirect(next_url)

        camera = get_object_or_404(Camera, sheet__number=sheet_num_int, side=side)
        pid = camera.motion_capture_pid
        if not pid:
            messages.info(request, "No running motion capture process was recorded for this camera.")
            return redirect(next_url)

        if _terminate_process(pid):
            camera.motion_capture_pid = None
            camera.save(update_fields=['motion_capture_pid'])
            messages.success(request, f"Stopped motion capture for Sheet {sheet_num} {side}.")
        else:
            messages.warning(request, "Could not confirm process termination; it may have already exited.")
            camera.motion_capture_pid = None
            camera.save(update_fields=['motion_capture_pid'])
        return redirect(next_url)
    return redirect('dashboard')


def _terminate_process(pid):
    try:
        if os.name == 'nt':
            os.kill(pid, signal.CTRL_BREAK_EVENT)
        else:
            os.kill(pid, signal.SIGTERM)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return False
