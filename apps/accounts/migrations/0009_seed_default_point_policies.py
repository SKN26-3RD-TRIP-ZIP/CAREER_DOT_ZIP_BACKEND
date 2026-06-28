from django.db import migrations
from django.utils import timezone


DEFAULT_POLICIES = [
    ('AUTH.EMAIL_VERIFIED', 'EARN', 100, None, None, True, False),
    ('PROFILE.COMPLETED', 'EARN', 500, None, None, True, False),
    ('PROFILE.DESIRED_JOB_SET', 'EARN', 200, None, None, True, False),
    ('JD.FIRST_CREATED', 'EARN', 500, None, None, True, False),
    ('RESUME.FIRST_CREATED', 'EARN', 500, None, None, True, False),
    ('COVER_LETTER.FIRST_CREATED', 'EARN', 500, None, None, True, False),
    ('PROJECT.FIRST_CREATED', 'EARN', 500, None, None, True, False),
    ('PROJECT.ADDITIONAL', 'EARN', 300, None, None, False, True),
    ('LOGIN.DAILY', 'EARN', 50, 50, 1500, False, True),
    ('LOGIN.STREAK_7', 'EARN', 200, None, 800, False, True),
    ('LOGIN.STREAK_30', 'EARN', 100, None, 100, False, True),
    ('INTERVIEW.COMPLETED', 'EARN', 300, 900, 9000, False, True),
    ('REPORT.FIRST_VIEWED', 'EARN', 100, 500, 3000, False, True),
    ('ACTION_PLAN.CREATED', 'EARN', 200, 600, 3000, False, True),
    ('INTERVIEW.WEAKNESS_SESSION_COMPLETED', 'EARN', 300, 900, 9000, False, True),
    ('DORMANT.RETURN_LOGIN', 'EARN', 300, None, None, True, False),
    ('INTERVIEW.EXTRA_SESSION', 'USE', -100, None, None, False, True),
    ('QUESTION_PACK.CUSTOM', 'USE', -500, None, None, False, True),
    ('PERSONA.ADVANCED', 'USE', -300, None, None, False, True),
    ('ANSWER.REEVALUATION', 'USE', -400, None, None, False, True),
    ('REPORT.DEEP_ANALYSIS', 'USE', -800, None, None, False, True),
    ('INTERVIEW.HINT', 'USE', -300, None, None, False, True),
    ('REPORT.GROWTH_COMPARE', 'USE', -600, None, None, False, True),
    ('PRACTICE.WEAKNESS_FOCUS', 'USE', -500, None, None, False, True),
    ('GITHUB.DEEP_ANALYSIS', 'USE', -700, None, None, False, True),
    ('ACTION_PLAN.REGENERATE', 'USE', -300, None, None, False, True),
]


def seed_policies(apps, schema_editor):
    PointPolicy = apps.get_model('accounts', 'PointPolicy')
    now = timezone.now()
    for reason_code, transaction_type, amount, daily_limit, monthly_limit, account_once, per_reference_once in DEFAULT_POLICIES:
        PointPolicy.objects.get_or_create(
            reason_code=reason_code,
            defaults={
                'transaction_type': transaction_type,
                'amount': amount,
                'daily_limit': daily_limit,
                'monthly_limit': monthly_limit,
                'account_once': account_once,
                'per_reference_once': per_reference_once,
                'is_active': True,
                'policy_version': '2026.06',
                'effective_start_at': now,
                'description': 'Career.zip default P0-P2 point policy',
            },
        )


def unseed_policies(apps, schema_editor):
    PointPolicy = apps.get_model('accounts', 'PointPolicy')
    PointPolicy.objects.filter(reason_code__in=[item[0] for item in DEFAULT_POLICIES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_pointpolicy_pointpolicychangelog_socialaccount_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_policies, unseed_policies),
    ]
