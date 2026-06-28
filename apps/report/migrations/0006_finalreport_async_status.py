from django.db import migrations, models


class Migration(migrations.Migration):
    """FinalReport 비동기 생성 상태 필드 추가.

    동시에 분기되어 있던 두 0005 리프(roadmap id alter / reportsharetoken)를
    단일 리프로 머지한다.
    """

    dependencies = [
        ('report', '0005_alter_roadmapcache_id_alter_roadmapitem_id'),
        ('report', '0005_reportsharetoken'),
    ]

    operations = [
        migrations.AddField(
            model_name='finalreport',
            name='status',
            # 기존 행은 이미 summary를 보유하므로 done 으로 채운다(하위호환).
            field=models.CharField(
                choices=[
                    ('pending', 'pending'),
                    ('processing', 'processing'),
                    ('done', 'done'),
                    ('failed', 'failed'),
                ],
                default='done',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='finalreport',
            name='error_code',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='finalreport',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
