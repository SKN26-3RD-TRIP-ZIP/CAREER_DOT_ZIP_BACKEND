from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.question_bank.models import QuestionBankItem
from apps.question_bank.services.aihub_parser import parse_aihub_file


class Command(BaseCommand):
    help = 'Import normalized ICT interview questions from local AI Hub JSON files.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path', '--input',
            dest='input_path',
            required=True,
            help='JSON file or directory to import from',
        )
        parser.add_argument('--limit', type=int, help='Maximum valid items to process')
        parser.add_argument('--dry-run', action='store_true', help='Parse without saving')
        parser.add_argument('--reset', action='store_true', help='Delete existing AI Hub items first')

    def handle(self, *args, **options):
        input_path = Path(options['input_path'])
        limit = options.get('limit')
        dry_run = options['dry_run']

        if not input_path.exists():
            raise CommandError(f'Input path does not exist: {input_path}')
        if limit is not None and limit < 1:
            raise CommandError('--limit must be greater than or equal to 1.')

        files = self._find_json_files(input_path)

        self.stdout.write('AI Hub question import started')
        self.stdout.write(f'path: {input_path}')
        self.stdout.write(f'found label json files: {len(files)}')

        stats = {
            'parsed_questions': 0,
            'created': 0,
            'skipped_duplicate': 0,
            'skipped_invalid': 0,
        }

        if options['reset'] and not dry_run:
            deleted, _ = QuestionBankItem.objects.filter(source='aihub').delete()
            self.stdout.write(f'reset: deleted {deleted} existing AI Hub items')

        valid_processed = 0
        for file_path in files:
            if limit is not None and valid_processed >= limit:
                break

            item_data = parse_aihub_file(str(file_path))
            if item_data is None:
                stats['skipped_invalid'] += 1
                continue

            valid_processed += 1
            stats['parsed_questions'] += 1

            lookup = {
                'source': item_data['source'],
                'source_file': item_data['source_file'],
                'question_text': item_data['question_text'],
            }
            if QuestionBankItem.objects.filter(**lookup).exists():
                stats['skipped_duplicate'] += 1
                continue

            if not dry_run:
                QuestionBankItem.objects.create(**item_data)
            stats['created'] += 1

        self.stdout.write(self.style.SUCCESS('AI Hub question import completed.'))
        for name, value in stats.items():
            self.stdout.write(f'- {name}: {value}')
        self.stdout.write(f'- dry_run: {str(dry_run).lower()}')

    @staticmethod
    def _find_json_files(input_path):
        if input_path.is_file():
            return [input_path] if input_path.suffix.lower() == '.json' else []
        return sorted(input_path.rglob('*.json'))
