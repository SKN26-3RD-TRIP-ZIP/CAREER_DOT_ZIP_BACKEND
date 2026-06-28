from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0002_generatedquestion_source_source_ref'),
    ]

    operations = [
        # AnalysisSession: career_level 추가 => 기존 모델에 넣어서 주석처리
        # migrations.AddField(
        #     model_name='analysissession',
        #     name='career_level',
        #     field=models.CharField(
        #         choices=[('entry', '신입'), ('experienced', '경력')],
        #         default='entry',
        #         max_length=20,
        #     ),
        # ), 

        # JdAnalysis: 점수 세분화 필드 추가
        migrations.AddField(
            model_name='jdanalysis',
            name='tech_score',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='jdanalysis',
            name='trait_score',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='jdanalysis',
            name='matched_keywords',
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name='jdanalysis',
            name='unmatched_keywords',
            field=models.JSONField(default=list),
        ),

        # JdAnalysis.jd_keywords: default를 dict로 변경
        migrations.AlterField(
            model_name='jdanalysis',
            name='jd_keywords',
            field=models.JSONField(default=dict),
        ),

        # AnalysisSession.jd_keywords: default를 dict로 변경
        migrations.AlterField(
            model_name='analysissession',
            name='jd_keywords',
            field=models.JSONField(default=dict),
        ),
    ]
