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
    path('calibrate/', views.trigger_calibrate, name='calibrate'),
    path('motion-capture/', views.trigger_motion_capture, name='motion_capture'),
    path('capture/', views.trigger_motion_capture, name='capture'),
    path('stop-motion-capture/', views.stop_motion_capture, name='stop_motion_capture'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
