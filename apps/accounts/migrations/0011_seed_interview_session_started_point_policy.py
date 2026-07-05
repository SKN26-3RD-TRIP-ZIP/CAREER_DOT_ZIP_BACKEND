from django.db import migrations
from django.utils import timezone


REASON_CODE = 'INTERVIEW.SESSION_STARTED'


def seed_policy(apps, schema_editor):
    PointPolicy = apps.get_model('accounts', 'PointPolicy')
    PointPolicy.objects.get_or_create(
        reason_code=REASON_CODE,
        defaults={
            'transaction_type': 'USE',
            'amount': -10,
            'daily_limit': None,
            'monthly_limit': None,
            'account_once': False,
            'per_reference_once': True,
            'is_active': True,
            'policy_version': '2026.06',
            'effective_start_at': timezone.now(),
            'description': 'Interview session start point charge',
        },
    )


def unseed_policy(apps, schema_editor):
    PointPolicy = apps.get_model('accounts', 'PointPolicy')
    PointPolicy.objects.filter(reason_code=REASON_CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_seed_default_terms_documents'),
    ]

    operations = [
        migrations.RunPython(seed_policy, unseed_policy),
    ]
