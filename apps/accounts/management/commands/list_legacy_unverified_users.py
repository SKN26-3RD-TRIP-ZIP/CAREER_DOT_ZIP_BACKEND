from django.core.management.base import BaseCommand

from apps.accounts.models import User


def _mask_email(email):
    local, _, domain = (email or '').partition('@')
    if not domain:
        return '***'
    head = local[:2] if len(local) >= 2 else local[:1]
    return f'{head}***@{domain}'


class Command(BaseCommand):
    help = 'List legacy unverified User rows without modifying production data.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument(
            '--show-email',
            action='store_true',
            help='Show raw email addresses for an approved operations check.',
        )

    def handle(self, *args, **options):
        limit = max(options['limit'], 1)
        show_email = options['show_email']
        users = (
            User.objects
            .filter(is_verified=False)
            .order_by('created_at')
            .values('id', 'email', 'status', 'created_at', 'updated_at')[:limit]
        )

        count = User.objects.filter(is_verified=False).count()
        self.stdout.write(f'Legacy unverified users: {count}')
        for user in users:
            email = user['email'] if show_email else _mask_email(user['email'])
            self.stdout.write(
                f'id={user["id"]} email={email} status={user["status"]} '
                f'created_at={user["created_at"].isoformat()} updated_at={user["updated_at"].isoformat()}'
            )
