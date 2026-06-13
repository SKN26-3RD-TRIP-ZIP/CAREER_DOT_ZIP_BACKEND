import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailVerificationCode',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('code_hash', models.CharField(max_length=128)),
                ('expires_at', models.DateTimeField()),
                ('attempt_count', models.PositiveSmallIntegerField(default=0)),
                ('is_used', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='email_codes',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'verbose_name': 'Email Verification Code',
                'verbose_name_plural': 'Email Verification Codes',
                'db_table': 'accounts_email_verification_code',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='emailverificationcode',
            index=models.Index(fields=['user', 'is_used'], name='evc_user_isused_idx'),
        ),
        migrations.AddIndex(
            model_name='emailverificationcode',
            index=models.Index(fields=['expires_at'], name='evc_expires_idx'),
        ),
    ]
