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
    path('capture/', views.trigger_capture, name='capture'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
