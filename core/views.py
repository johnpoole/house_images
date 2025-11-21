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

def trigger_capture(request):
    if request.method == 'POST':
        sheet_num = request.POST.get('sheet_id')
        side = request.POST.get('side')
        next_url = request.POST.get('next', 'dashboard')
        try:
            call_command('capture', sheet=int(sheet_num), camera=side, poll_interval=1.0, threshold=5.0, max_frames=1)
            messages.success(request, f"Captured frame for Sheet {sheet_num} {side}")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
        return redirect(next_url)
    return redirect('dashboard')
