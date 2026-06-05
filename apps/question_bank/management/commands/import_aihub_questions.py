import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.question_bank.models import QuestionBankItem
from apps.question_bank.services.aihub_parser import parse_aihub_file


class Command(BaseCommand):
    help = 'Import normalized ICT interview questions from local AI Hub JSON files.'

    def add_arguments(self, parser):
        parser.add_argument('--input', required=True, help='JSON file or directory')
        parser.add_argument('--limit', type=int, help='Maximum valid items to process')
        parser.add_argument('--dry-run', action='store_true', help='Parse without saving')
        parser.add_argument('--reset', action='store_true', help='Delete existing AI Hub items first')

    def handle(self, *args, **options):
        input_path = Path(options['input'])
        limit = options.get('limit')
        dry_run = options['dry_run']
        if not input_path.exists():
            raise CommandError(f'Input path does not exist: {input_path}')
        if limit is not None and limit < 1:
            raise CommandError('--limit must be greater than or equal to 1.')

        files = self._find_json_files(input_path)
        stats = {
            'scanned': 0,
            'imported': 0,
            'skipped_non_ict': 0,
            'skipped_invalid': 0,
            'duplicated': 0,
        }
        if options['reset'] and not dry_run:
            QuestionBankItem.objects.filter(source='aihub').delete()

        valid_processed = 0
        for file_path in files:
            if limit is not None and valid_processed >= limit:
                break
            stats['scanned'] += 1
            item_data = parse_aihub_file(str(file_path))
            if item_data is None:
                stats[self._skip_reason(file_path)] += 1
                continue

            valid_processed += 1
            lookup = {
                'source': item_data['source'],
                'source_file': item_data['source_file'],
                'question_text': item_data['question_text'],
            }
            if QuestionBankItem.objects.filter(**lookup).exists():
                stats['duplicated'] += 1
                continue
            if not dry_run:
                QuestionBankItem.objects.create(**item_data)
            stats['imported'] += 1

        self.stdout.write(self.style.SUCCESS('AI Hub question import completed.'))
        for name, value in stats.items():
            self.stdout.write(f'- {name}: {value}')
        if dry_run:
            self.stdout.write('- dry_run: no database changes')

    @staticmethod
    def _find_json_files(input_path):
        if input_path.is_file():
            return [input_path] if input_path.suffix.lower() == '.json' else []
        return sorted(input_path.rglob('*.json'))

    @staticmethod
    def _skip_reason(file_path):
        try:
            with file_path.open(encoding='utf-8') as file:
                payload = json.load(file)
            dataset = payload.get('dataSet') or payload.get('dataset') or {}
            occupation = str((dataset.get('info') or {}).get('occupation') or '')
            if occupation and occupation.upper() != 'ICT':
                return 'skipped_non_ict'
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            pass
        return 'skipped_invalid'
