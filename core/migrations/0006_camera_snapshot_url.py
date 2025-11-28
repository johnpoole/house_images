from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_calibrationsession_calibrationlinepoint'),
    ]

    operations = [
        migrations.AddField(
            model_name='camera',
            name='snapshot_url',
            field=models.URLField(
                blank=True,
                help_text='HTTP endpoint that returns the latest JPEG still for this camera',
            ),
        ),
        migrations.AlterField(
            model_name='camera',
            name='device_index',
            field=models.IntegerField(
                blank=True,
                help_text='Local camera device index (e.g. 0, 1, 2)',
                null=True,
            ),
        ),
    ]
