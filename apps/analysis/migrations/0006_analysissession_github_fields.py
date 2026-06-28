from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0005_question_regeneration_and_feedback'),
    ]

    operations = [
        migrations.AddField(
            model_name='analysissession',
            name='github_url',
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='analysissession',
            name='github_summary',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
