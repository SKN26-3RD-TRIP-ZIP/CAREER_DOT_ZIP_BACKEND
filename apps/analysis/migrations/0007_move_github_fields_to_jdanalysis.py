from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0006_analysissession_github_fields'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='analysissession',
            name='github_url',
        ),
        migrations.RemoveField(
            model_name='analysissession',
            name='github_summary',
        ),
        migrations.AddField(
            model_name='jdanalysis',
            name='github_url',
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='jdanalysis',
            name='github_summary',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
