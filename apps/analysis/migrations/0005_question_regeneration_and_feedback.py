import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analysis', '0004_analysissession_career_level'),
    ]

    operations = [
        migrations.AddField(
            model_name='jdanalysis',
            name='generation_count',
            field=models.IntegerField(default=0),
        ),
        migrations.CreateModel(
            name='QuestionFeedback',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('rating', models.CharField(choices=[('up', '만족'), ('down', '불만족')], max_length=10)),
                ('generation_count', models.IntegerField(default=0)),
                ('comment', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('jd_analysis', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='feedbacks', to='analysis.jdanalysis')),
            ],
            options={
                'db_table': 'analysis_question_feedback',
                'ordering': ['-created_at'],
            },
        ),
    ]
