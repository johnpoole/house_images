import json
import os
import shutil

from django.conf import settings
from django.db.models import Prefetch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from core.calibration_pipeline import CalibrationComputationError
from core.calibration_service import create_calibration_session
from core.capture_utils import capture_single_frame
from core.network_utils import detect_ipv4_prefix, scan_snapshot_hosts
from .platform_utils import (
    get_background_python_executable,
    launch_detached_process,
    terminate_process,
)
from .models import Sheet, Camera, CapturedFrame, CalibrationArtifact, CalibrationSession
from .utils import labeled_camera_choices, list_available_cameras


def _frame_exists(frame):
    if not frame or not frame.image or not frame.image.name:
        return False
    try:
        return os.path.exists(frame.image.path)
    except (ValueError, OSError):
        return False

def dashboard(request):
    sheets = Sheet.objects.all().order_by('number')
    return render(request, 'core/dashboard.html', {'sheets': sheets})

def _ensure_frame_available(camera, frame=None):
    if frame and frame.image and frame.image.name:
        try:
            if os.path.exists(frame.image.path):
                return frame
        except (ValueError, OSError):
            pass
        frame.delete()
    try:
        return capture_single_frame(camera)
    except RuntimeError as exc:
        messages.warning(
            None,
            f"{camera.get_side_display()} camera: {exc}",
        )
        return None


def sheet_detail(request, sheet_id):
    sheet = get_object_or_404(Sheet, number=sheet_id)

    available_indices = list_available_cameras(max_range=4)
    available_cameras = labeled_camera_choices(max_range=4)

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
    session_prefetch = Prefetch(
        'calibration_sessions',
        queryset=CalibrationSession.objects.order_by('-created_at'),
        to_attr='prefetched_sessions'
    )

    camera_cards = []
    cameras = Camera.objects.filter(sheet=sheet).prefetch_related(
        frame_prefetch,
        artifact_prefetch,
        session_prefetch,
    )
    for cam in cameras:
        last_frame = cam.prefetched_frames[0] if cam.prefetched_frames else None
        if last_frame and not _frame_exists(last_frame):
            last_frame.delete()
            last_frame = None
        if last_frame is None:
            try:
                last_frame = capture_single_frame(cam)
                messages.info(
                    request,
                    f"Captured a still for {cam.get_side_display()} camera to seed calibration.",
                )
            except RuntimeError as exc:
                messages.warning(request, f"{cam.get_side_display()} camera: {exc}")
        last_artifact = cam.prefetched_artifacts[0] if cam.prefetched_artifacts else None
        pending_session = None
        for session in getattr(cam, 'prefetched_sessions', []):
            if session.status == CalibrationSession.Status.PENDING:
                pending_session = session
                break
        pending_meta = None
        if pending_session:
            crop = pending_session.crop_rect or {}
            crop_text = None
            if crop:
                crop_text = f"({crop.get('x', '?')}, {crop.get('y', '?')}) {crop.get('w', '?')}x{crop.get('h', '?')}"
            best_combo = None
            if pending_session.metadata:
                best_combo = pending_session.metadata.get('best_combo')
            pending_meta = {
                'crop_text': crop_text,
                'best_combo': best_combo,
            }
        camera_cards.append({
            'camera': cam,
            'last_frame': last_frame,
            'last_artifact': last_artifact,
            'pending_session': pending_session,
            'pending_meta': pending_meta,
        })

    return render(request, 'core/sheet_detail.html', {
        'sheet': sheet,
        'available_indices': available_indices,
        'available_cameras': available_cameras,
        'camera_cards': camera_cards,
    })

def update_camera(request):
    if request.method == 'POST':
        sheet_num = request.POST.get('sheet_id')
        side = request.POST.get('side')
        new_index = request.POST.get('device_index')
        snapshot_url = (request.POST.get('snapshot_url') or '').strip()
        
        try:
            camera = Camera.objects.get(sheet__number=sheet_num, side=side)
            update_fields = []
            if new_index is not None:
                new_index = new_index.strip()
                if new_index == '':
                    camera.device_index = None
                else:
                    camera.device_index = int(new_index)
                update_fields.append('device_index')
            camera.snapshot_url = snapshot_url
            update_fields.append('snapshot_url')
            camera.save(update_fields=update_fields)
            if not camera.snapshot_url and camera.device_index is None:
                messages.warning(request, f"{side.capitalize()} camera has no capture source configured.")
            else:
                source_desc = camera.snapshot_url or (
                    f"Device {camera.device_index}" if camera.device_index is not None else 'Unassigned'
                )
                messages.success(request, f"Updated {side} camera source to {source_desc}")
        except Exception as exc:
            messages.error(request, f"Error updating camera: {exc}")
            
        return redirect('sheet_detail', sheet_id=sheet_num)
    return redirect('dashboard')

def start_calibration(request, sheet_id, side):
    side = side.lower()
    if side not in ('odd', 'even'):
        messages.error(request, "Invalid camera side supplied for calibration.")
        return redirect('sheet_detail', sheet_id=sheet_id)

    camera = get_object_or_404(Camera, sheet__number=sheet_id, side=side)
    frame = camera.frames.order_by('-timestamp').first()
    if frame and not _frame_exists(frame):
        frame.delete()
        frame = None
    if not frame:
        try:
            frame = capture_single_frame(camera)
            messages.info(request, "Captured a fresh still from the camera for calibration.")
        except RuntimeError as exc:
            messages.error(request, str(exc))
            return redirect('sheet_detail', sheet_id=sheet_id)

    context = {
        'sheet': camera.sheet,
        'camera': camera,
        'frame': frame,
        'image_url': request.build_absolute_uri(frame.image.url),
        'next': request.GET.get('next') or request.META.get('HTTP_REFERER') or '',
    }
    return render(request, 'core/calibration.html', context)


@require_POST
def submit_calibration(request):
    sheet_num = request.POST.get('sheet_id')
    side = request.POST.get('side')
    frame_id = request.POST.get('frame_id')
    next_url = request.POST.get('next') or None
    lines_json = request.POST.get('lines_json')

    if not all([sheet_num, side, frame_id, lines_json]):
        messages.error(request, "Missing calibration data; please try again.")
        return redirect(next_url or 'dashboard')

    try:
        frame = CapturedFrame.objects.select_related('camera', 'camera__sheet').get(id=int(frame_id))
    except (CapturedFrame.DoesNotExist, ValueError):
        messages.error(request, "Selected frame is no longer available.")
        return redirect(next_url or 'dashboard')

    camera = frame.camera
    if str(camera.sheet.number) != str(sheet_num) or camera.side != side:
        messages.error(request, "Calibration request did not match the selected camera.")
        return redirect('sheet_detail', sheet_id=camera.sheet.number)

    try:
        parsed_lines = json.loads(lines_json)
    except json.JSONDecodeError:
        messages.error(request, "Unable to parse the clicked line data; please retry.")
        return redirect('sheet_detail', sheet_id=camera.sheet.number)

    if not isinstance(parsed_lines, list) or len(parsed_lines) < 3:
        messages.error(request, "Please trace all three sheet lines before saving.")
        return redirect('start_calibration', sheet_id=camera.sheet.number, side=camera.side)

    image_path = frame.image.path
    if not os.path.exists(image_path):
        messages.error(request, "Raw frame file is missing from disk; capture a new frame and try again.")
        return redirect('sheet_detail', sheet_id=camera.sheet.number)

    try:
        create_calibration_session(camera, image_path, parsed_lines)
    except CalibrationComputationError as exc:
        messages.error(request, str(exc))
        return redirect('sheet_detail', sheet_id=camera.sheet.number)

    messages.success(request, "Calibration session recorded. Review the preview on the sheet page to accept it.")
    return redirect('sheet_detail', sheet_id=camera.sheet.number)


def accept_calibration(request):
    if request.method == 'POST':
        session_id = request.POST.get('session_id')
        next_url = request.POST.get('next', 'dashboard')
        session = get_object_or_404(
            CalibrationSession,
            id=session_id,
            status=CalibrationSession.Status.PENDING,
        )

        if not session.artifact_dir:
            messages.error(request, "Calibration session has no staged artifacts to accept.")
            return redirect(next_url)

        artifact_dir = os.path.join(settings.BASE_DIR, session.artifact_dir)
        required_files = [
            'camera_matrix.npy',
            'dist_coeffs.npy',
            'new_camera_matrix.npy',
            'crop_rect.npy',
        ]
        missing = [name for name in required_files if not os.path.exists(os.path.join(artifact_dir, name))]
        if missing:
            messages.error(request, f"Missing staged artifacts: {', '.join(missing)}")
            return redirect(next_url)

        camera = session.camera
        relative_final = os.path.join('calibration', f"sheet{camera.sheet.number}_{camera.side}")
        absolute_final = os.path.join(settings.BASE_DIR, relative_final)
        os.makedirs(absolute_final, exist_ok=True)

        for filename in required_files:
            shutil.copy2(os.path.join(artifact_dir, filename), os.path.join(absolute_final, filename))
        optional_previews = ['undistorted_preview.jpg', 'rectified_preview.jpg']
        for preview in optional_previews:
            source_path = os.path.join(artifact_dir, preview)
            if os.path.exists(source_path):
                shutil.copy2(source_path, os.path.join(absolute_final, preview))

        camera.calibration_dir = relative_final
        camera.is_calibrated = True
        camera.save(update_fields=['calibration_dir', 'is_calibrated'])

        session.status = CalibrationSession.Status.ACCEPTED
        session.save(update_fields=['status'])

        CalibrationArtifact.objects.create(
            camera=camera,
            artifact_type=CalibrationArtifact.ArtifactType.OTHER,
            data={
                'session_id': session.id,
                'fit_error': session.fit_error,
                'crop_rect': session.crop_rect,
                'best_combo': session.metadata.get('best_combo') if session.metadata else None,
            },
            notes='Calibration accepted via Django UI',
        )

        messages.success(request, f"Calibration accepted for Sheet {camera.sheet.number} {camera.side} camera.")
        return redirect(next_url)
    return redirect('dashboard')


def reject_calibration(request):
    if request.method == 'POST':
        session_id = request.POST.get('session_id')
        next_url = request.POST.get('next', 'dashboard')
        session = get_object_or_404(
            CalibrationSession,
            id=session_id,
            status=CalibrationSession.Status.PENDING,
        )

        if session.rectified_preview:
            session.rectified_preview.delete(save=False)
        if session.source_image:
            session.source_image.delete(save=False)

        if session.artifact_dir:
            artifact_dir = os.path.join(settings.BASE_DIR, session.artifact_dir)
            shutil.rmtree(artifact_dir, ignore_errors=True)

        session.artifact_dir = ''
        session.status = CalibrationSession.Status.REJECTED
        session.save(update_fields=['status', 'artifact_dir'])
        messages.info(request, "Calibration run rejected.")
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
        python_exec = get_background_python_executable()
        cmd = [python_exec, manage_py, 'capture', '--sheet', str(sheet_num_int), '--camera', side]

        try:
            proc = launch_detached_process(cmd, cwd=settings.BASE_DIR)
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

        if terminate_process(pid):
            camera.motion_capture_pid = None
            camera.save(update_fields=['motion_capture_pid'])
            messages.success(request, f"Stopped motion capture for Sheet {sheet_num} {side}.")
        else:
            messages.warning(request, "Could not confirm process termination; it may have already exited.")
            camera.motion_capture_pid = None
            camera.save(update_fields=['motion_capture_pid'])
        return redirect(next_url)
    return redirect('dashboard')


def scan_snapshot_cameras(request):
    prefix = detect_ipv4_prefix()
    if not prefix:
        return JsonResponse({'error': 'Unable to determine local IPv4 network.'}, status=503)
    hosts = scan_snapshot_hosts(prefix)
    payload = [
        {
            'ip': host.ip,
            'url': host.url,
            'status_code': host.status_code,
            'content_type': host.content_type,
            'content_length': host.content_length,
        }
        for host in hosts
    ]
    return JsonResponse({'subnet': f'{prefix}.0/24', 'hosts': payload})
