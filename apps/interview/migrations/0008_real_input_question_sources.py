# Generated manually for real input question source tracking.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('interview', '0007_interviewanswer_audio_url_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='interviewquestion',
            name='source_type',
            field=models.CharField(
                choices=[
                    ('jd', 'JD'),
                    ('resume', 'Resume'),
                    ('cover_letter', 'Cover Letter'),
                    ('project', 'Project'),
                    ('project_experience', 'Project Experience'),
                    ('combined', 'Combined'),
                    ('prepared_question', 'Prepared Question'),
                    ('question_bank', 'Question Bank'),
                    ('profile', 'Profile'),
                    ('rule', 'Rule'),
                    ('general', 'General'),
                ],
                default='general',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='interviewquestion',
            name='difficulty',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.CreateModel(
            name='QuestionSourceTag',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('source_type', models.CharField(
                    choices=[
                        ('jd', 'JD'),
                        ('resume', 'Resume'),
                        ('cover_letter', 'Cover Letter'),
                        ('project', 'Project'),
                        ('project_experience', 'Project Experience'),
                        ('combined', 'Combined'),
                        ('prepared_question', 'Prepared Question'),
                        ('question_bank', 'Question Bank'),
                        ('profile', 'Profile'),
                        ('rule', 'Rule'),
                        ('general', 'General'),
                    ],
                    default='general',
                    max_length=30,
                )),
                ('source_label', models.CharField(blank=True, default='', max_length=100)),
                ('source_text_excerpt', models.TextField(blank=True, default='')),
                ('source_reference', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('question', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='source_tags',
                    to='interview.interviewquestion',
                )),
            ],
            options={
                'db_table': 'question_source_tags',
                'ordering': ['id'],
            },
        ),
    ]
