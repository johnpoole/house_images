from django.db import models

class Sheet(models.Model):
    number = models.IntegerField(unique=True)

    def __str__(self):
        return f"Sheet {self.number}"

class Camera(models.Model):
    SIDE_CHOICES = [
        ('odd', 'Odd'),
        ('even', 'Even'),
    ]
    sheet = models.ForeignKey(Sheet, on_delete=models.CASCADE, related_name='cameras')
    side = models.CharField(max_length=4, choices=SIDE_CHOICES)
    device_index = models.IntegerField(help_text="Camera device index (e.g. 0, 1, 2)")
    is_calibrated = models.BooleanField(default=False)
    calibration_dir = models.CharField(max_length=255, blank=True, help_text="Path to calibration files")

    class Meta:
        unique_together = ('sheet', 'side')

    def __str__(self):
        return f"Sheet {self.sheet.number} - {self.get_side_display()}"

class CapturedFrame(models.Model):
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name='frames')
    image = models.ImageField(upload_to='frames/')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.camera} - {self.timestamp}"
