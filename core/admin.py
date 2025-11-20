from django.contrib import admin
from .models import Sheet, Camera, CapturedFrame

@admin.register(Sheet)
class SheetAdmin(admin.ModelAdmin):
    list_display = ('number',)

@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = ('sheet', 'side', 'device_index', 'is_calibrated')
    list_filter = ('sheet', 'side', 'is_calibrated')

@admin.register(CapturedFrame)
class CapturedFrameAdmin(admin.ModelAdmin):
    list_display = ('camera', 'timestamp')
    list_filter = ('camera__sheet', 'camera__side')
