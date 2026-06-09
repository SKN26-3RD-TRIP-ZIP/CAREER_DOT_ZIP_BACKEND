"""
사용법:
  python manage.py embed_question_bank
  python manage.py embed_question_bank --batch-size 50
  python manage.py embed_question_bank --dry-run
  python manage.py embed_question_bank --index my-index --batch-size 200
"""

from django.core.management.base import BaseCommand

from apps.question_bank.services.embedding_service import run_full_pipeline


class Command(BaseCommand):
    help = "QuestionBankItem을 임베딩해 Pinecone에 적재합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--index",
            type=str,
            default=None,
            help="Pinecone 인덱스 이름 (기본값: settings.PINECONE_INDEX_NAME)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="한 번에 처리할 항목 수 (기본값: 100)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="실제 Pinecone 저장 없이 전처리 결과만 확인",
        )

    def handle(self, *args, **options):
        stats = run_full_pipeline(
            pinecone_index_name=options["index"],
            batch_size=options["batch_size"],
            dry_run=options["dry_run"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"완료 — total={stats['total']} upserted={stats['upserted']} "
                f"skipped={stats['skipped']} failed={stats['failed']}"
            )
        )
