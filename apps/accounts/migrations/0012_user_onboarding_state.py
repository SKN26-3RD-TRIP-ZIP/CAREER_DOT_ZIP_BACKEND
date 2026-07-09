from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_seed_interview_session_started_point_policy'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='onboarding_completed_at',
            field=models.DateTimeField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='onboarding_version',
            field=models.PositiveSmallIntegerField(default=1),
        ),
    ]
