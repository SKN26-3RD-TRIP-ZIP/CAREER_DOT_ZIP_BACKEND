from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='status',
            field=models.CharField(
                choices=[('active', 'Active'), ('dormant', 'Dormant'), ('banned', 'Banned')],
                default='active',
                max_length=20,
            ),
        ),
    ]
