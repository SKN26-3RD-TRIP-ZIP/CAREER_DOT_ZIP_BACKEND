from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='generatedquestion',
            name='source',
            field=models.CharField(
                choices=[
                    ('jd',           '채용공고(JD)'),
                    ('resume',       '이력서'),
                    ('cover_letter', '자기소개서'),
                    ('project',      '프로젝트 경험'),
                    ('combined',     '복합 출처'),
                ],
                default='jd',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='generatedquestion',
            name='source_ref',
            field=models.TextField(blank=True, default=''),
        ),
    ]
