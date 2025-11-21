from django.contrib import admin
from .models import Sheet, Camera, CapturedFrame, CalibrationArtifact

@admin.register(Sheet)
class SheetAdmin(admin.ModelAdmin):
    list_display = ('number',)

@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = ('sheet', 'side', 'device_index', 'is_calibrated')
    list_filter = ('sheet', 'side', 'is_calibrated')

@admin.register(CapturedFrame)
class CapturedFrameAdmin(admin.ModelAdmin):
    list_display = ('camera', 'timestamp', 'has_rectified_image')
    list_filter = ('camera__sheet', 'camera__side')

    @admin.display(boolean=True, description='Rectified Saved')
    def has_rectified_image(self, obj):
        return bool(obj.rectified_image)


@admin.register(CalibrationArtifact)
class CalibrationArtifactAdmin(admin.ModelAdmin):
    list_display = ('camera', 'artifact_type', 'created_at')
    list_filter = ('artifact_type', 'camera__sheet', 'camera__side')
