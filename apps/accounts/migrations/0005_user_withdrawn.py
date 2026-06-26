from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_add_dormancy_warning_sent_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='withdrawn_at',
            field=models.DateTimeField(blank=True, default=None, null=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='status',
            field=models.CharField(
                choices=[
                    ('active', 'Active'),
                    ('dormant', 'Dormant'),
                    ('banned', 'Banned'),
                    ('withdrawn', 'Withdrawn'),
                ],
                default='active',
                max_length=20,
            ),
        ),
    ]
