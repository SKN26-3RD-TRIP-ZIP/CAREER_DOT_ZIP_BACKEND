from django.db import migrations
from django.utils import timezone


DEFAULT_DOCUMENTS = [
    ('TERMS', 'v1', 'Career.zip Terms of Service', True),
    ('PRIVACY', 'v1', 'Career.zip Privacy Policy', True),
    ('MARKETING', 'v1', 'Career.zip Marketing Consent', False),
]


def seed_terms_documents(apps, schema_editor):
    TermsDocument = apps.get_model('accounts', 'TermsDocument')
    now = timezone.now()
    for kind, version, title, is_required in DEFAULT_DOCUMENTS:
        TermsDocument.objects.get_or_create(
            kind=kind,
            version=version,
            defaults={
                'title': title,
                'content_hash': '',
                'is_required': is_required,
                'is_active': True,
                'effective_at': now,
                'retention_policy': 'Preserve consent history after withdrawal according to privacy policy.',
            },
        )


def unseed_terms_documents(apps, schema_editor):
    TermsDocument = apps.get_model('accounts', 'TermsDocument')
    for kind, version, _title, _required in DEFAULT_DOCUMENTS:
        TermsDocument.objects.filter(kind=kind, version=version).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_seed_default_point_policies'),
    ]

    operations = [
        migrations.RunPython(seed_terms_documents, unseed_terms_documents),
    ]
