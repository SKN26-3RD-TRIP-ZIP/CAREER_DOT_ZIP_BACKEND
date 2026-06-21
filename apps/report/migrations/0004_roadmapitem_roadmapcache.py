# Generated migration for RoadmapItem and RoadmapCache models

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('interview', '0010_interviewquestion_question_category'),
        ('report', '0003_alter_finalreport_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='RoadmapItem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('item_id', models.CharField(max_length=50)),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField()),
                ('priority', models.CharField(choices=[('high', 'high'), ('mid', 'mid'), ('low', 'low')], max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('session', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='roadmap_items',
                    to='interview.interviewsession',
                )),
            ],
            options={
                'db_table': 'roadmap_items',
                'ordering': ['created_at'],
            },
        ),
        migrations.CreateModel(
            name='RoadmapCache',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('week_priority_text', models.TextField()),
                ('practice_question', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('session', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='roadmap_cache',
                    to='interview.interviewsession',
                )),
            ],
            options={
                'db_table': 'roadmap_cache',
            },
        ),
    ]
