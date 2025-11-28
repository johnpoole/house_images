from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.dashboard, name='dashboard'),
    path('sheet/<int:sheet_id>/', views.sheet_detail, name='sheet_detail'),
    path('update_camera/', views.update_camera, name='update_camera'),
    path('calibration/start/<int:sheet_id>/<str:side>/', views.start_calibration, name='start_calibration'),
    path('calibration/submit/', views.submit_calibration, name='submit_calibration'),
    path('calibration/accept/', views.accept_calibration, name='accept_calibration'),
    path('calibration/reject/', views.reject_calibration, name='reject_calibration'),
    path('motion-capture/', views.trigger_motion_capture, name='motion_capture'),
    path('capture/', views.trigger_motion_capture, name='capture'),
    path('stop-motion-capture/', views.stop_motion_capture, name='stop_motion_capture'),
    path('api/scan-cameras/', views.scan_snapshot_cameras, name='scan_snapshot_cameras'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
