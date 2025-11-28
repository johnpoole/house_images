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
    device_index = models.IntegerField(
        null=True,
        blank=True,
        help_text="Local camera device index (e.g. 0, 1, 2)",
    )
    snapshot_url = models.URLField(
        blank=True,
        help_text="HTTP endpoint that returns the latest JPEG still for this camera",
    )
    is_calibrated = models.BooleanField(default=False)
    calibration_dir = models.CharField(max_length=255, blank=True, help_text="Path to calibration files")
    motion_capture_pid = models.IntegerField(null=True, blank=True, help_text="PID of the running capture process, if any")

    class Meta:
        unique_together = ('sheet', 'side')

    def __str__(self):
        return f"Sheet {self.sheet.number} - {self.get_side_display()}"

class CapturedFrame(models.Model):
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name='frames')
    image = models.ImageField(upload_to='frames/')
    rectified_image = models.ImageField(upload_to='frames/rectified/', blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.camera} - {self.timestamp}"


class CalibrationArtifact(models.Model):
    class ArtifactType(models.TextChoices):
        LINE_POINTS = ('line_points', 'Line Points')
        HOMOGRAPHY = ('homography', 'Homography Matrix')
        RADIAL = ('radial', 'Radial Distortion')
        OTHER = ('other', 'Other')

    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name='calibration_artifacts')
    artifact_type = models.CharField(max_length=32, choices=ArtifactType.choices, default=ArtifactType.LINE_POINTS)
    data = models.JSONField(default=dict, blank=True)
    source_image_path = models.CharField(max_length=255, blank=True)
    artifact_file = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.camera} - {self.get_artifact_type_display()} ({self.created_at:%Y-%m-%d %H:%M:%S})"


class CalibrationSession(models.Model):
    class Status(models.TextChoices):
        PENDING = ('pending', 'Pending')
        ACCEPTED = ('accepted', 'Accepted')
        REJECTED = ('rejected', 'Rejected')

    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name='calibration_sessions')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    source_image = models.ImageField(upload_to='calibration/source/')
    rectified_preview = models.ImageField(upload_to='calibration/preview/', blank=True, null=True)
    fit_error = models.FloatField(blank=True, null=True)
    crop_rect = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    artifact_dir = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Calibration session {self.id} for {self.camera} ({self.get_status_display()})"


class CalibrationLinePoint(models.Model):
    session = models.ForeignKey(CalibrationSession, on_delete=models.CASCADE, related_name='line_points')
    line_index = models.IntegerField()
    point_index = models.IntegerField()
    x = models.IntegerField()
    y = models.IntegerField()

    class Meta:
        ordering = ['line_index', 'point_index']

    def __str__(self):
        return f"Session {self.session_id} line {self.line_index} point {self.point_index}"
