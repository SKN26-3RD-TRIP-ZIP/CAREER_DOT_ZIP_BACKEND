from django.db import migrations, models
from django.db.utils import ProgrammingError, OperationalError


def migrate_pressure_to_verifier(apps, schema_editor):
    try:
        schema_editor.execute(
            "UPDATE interview_interviewsession SET persona = 'verifier' WHERE persona = 'pressure'"
        )
    except (ProgrammingError, OperationalError):
        pass  # 테이블이 없으면 변환할 데이터도 없음


class Migration(migrations.Migration):

    dependencies = [
        ('interview', '0008_real_input_question_sources'),
    ]

    operations = [
        migrations.RunPython(migrate_pressure_to_verifier, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='interviewsession',
            name='persona',
            field=models.CharField(
                choices=[
                    ('coach', '코치형'),
                    ('practical', '실무형'),
                    ('verifier', '검증형'),
                ],
                max_length=20,
            ),
        ),
    ]
