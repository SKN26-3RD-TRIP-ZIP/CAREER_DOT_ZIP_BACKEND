# Generated manually for E7.4 (emotion_intent_score), E7.6 (pause_analysis),
# and E7.7 (ABTestExperiment / ABTestAssignment / ABTestResult).

import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0001_initial'),
    ]

    operations = [
        # ── E7.4 / E7.6 — Evaluation 새 필드 ────────────────────────────
        migrations.AddField(
            model_name='evaluation',
            name='emotion_intent_score',
            field=models.JSONField(blank=True, default=dict,
                                   help_text='E7.4 감정/의도 분류 결과 (확률값 + 신뢰도 보정)'),
        ),
        migrations.AddField(
            model_name='evaluation',
            name='pause_analysis',
            field=models.JSONField(blank=True, default=dict,
                                   help_text='E7.6 고도화 휴지 패턴 분석 결과'),
        ),

        # ── E7.7 — A/B 테스트 테이블 ─────────────────────────────────────
        migrations.CreateModel(
            name='ABTestExperiment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100, unique=True,
                                          help_text='실험 식별자 (예: eval_method_v2)')),
                ('description', models.TextField(blank=True)),
                ('target_metric', models.CharField(max_length=100)),
                ('treatment_ratio', models.FloatField(default=0.5)),
                ('status', models.CharField(
                    max_length=20,
                    choices=[('active', '진행 중'), ('paused', '일시 중단'), ('completed', '종료')],
                    default='active',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'db_table': 'ab_test_experiments',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ABTestAssignment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ('experiment', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='assignments',
                    to='evaluation.abtestexperiment',
                )),
                ('user_id', models.UUIDField(db_index=True)),
                ('variant', models.CharField(
                    max_length=20,
                    choices=[('control', '대조군'), ('treatment', '실험군')],
                )),
                ('assigned_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'ab_test_assignments',
                'ordering': ['-assigned_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='abtestassignment',
            constraint=models.UniqueConstraint(
                fields=['experiment', 'user_id'],
                name='unique_ab_assignment',
            ),
        ),
        migrations.CreateModel(
            name='ABTestResult',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ('experiment', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='results',
                    to='evaluation.abtestexperiment',
                )),
                ('assignment', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='results',
                    to='evaluation.abtestassignment',
                )),
                ('answer_id', models.UUIDField(db_index=True)),
                ('final_score', models.FloatField(blank=True, null=True)),
                ('bei_total', models.FloatField(blank=True, null=True)),
                ('cbi_score', models.FloatField(blank=True, null=True)),
                ('grounding_score', models.FloatField(blank=True, null=True)),
                ('speech_score', models.FloatField(blank=True, null=True)),
                ('sbert_score', models.FloatField(blank=True, null=True)),
                ('emotion_confidence', models.FloatField(blank=True, null=True)),
                ('extra_metrics', models.JSONField(blank=True, default=dict)),
                ('recorded_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'ab_test_results',
                'ordering': ['-recorded_at'],
            },
        ),
    ]
