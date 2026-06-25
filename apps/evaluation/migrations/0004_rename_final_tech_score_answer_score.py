# Generated 2026-06-25 — Evaluation.final_tech_score -> answer_score
# 비기술 답변 점수까지 담으면서 이름과 의미가 어긋나 answer_score로 변경.
# 모델에는 읽기 호환용 @property final_tech_score를 임시로 유지(인터뷰 팀 turns
# serializer 마이그레이션 전까지). DB 컬럼명만 rename한다.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0003_fix_abtestassignment_user_id'),
    ]

    operations = [
        migrations.RenameField(
            model_name='evaluation',
            old_name='final_tech_score',
            new_name='answer_score',
        ),
    ]
