from django.shortcuts import render, redirect, get_object_or_404
from django.core.management import call_command
from django.contrib import messages
from .models import Sheet, Camera
from .utils import list_available_cameras

def dashboard(request):
    sheets = Sheet.objects.all().order_by('number')
    return render(request, 'core/dashboard.html', {'sheets': sheets})

def sheet_detail(request, sheet_id):
    sheet = get_object_or_404(Sheet, number=sheet_id)
    # In a real scenario, caching this list is better as probing is slow
    # For now, we probe on every load or maybe just pass a static range if probing is too slow
    # Let's try probing first, but limit range.
    available_indices = list_available_cameras(max_range=4) 
    # If probing is too slow/unreliable, we might just provide a list of 0-10
    
    return render(request, 'core/sheet_detail.html', {
        'sheet': sheet,
        'available_indices': available_indices
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
            call_command('calibrate', sheet=sheet_num, camera=side)
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
            # For MVP, we just log it. In production this would start a background job.
            # Or we could actually run a "snapshot" command here if we want immediate feedback.
            # Let's try to run the capture command for a short burst or single frame if we modify it.
            # For now, just message.
            messages.info(request, f"Capture triggered for Sheet {sheet_num} {side}")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
        return redirect(next_url)
    return redirect('dashboard')
