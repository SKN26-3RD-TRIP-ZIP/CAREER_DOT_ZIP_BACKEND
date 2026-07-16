from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('interview', '0012_questionpack_guardrailevent_direction_and_more')]

    operations = [
        migrations.AddField(
            model_name='interviewanswer',
            name='audio_key',
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
    ]
