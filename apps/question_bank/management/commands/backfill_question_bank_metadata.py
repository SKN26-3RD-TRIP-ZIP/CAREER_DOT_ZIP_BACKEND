import hashlib
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.question_bank.models import QuestionBankItem


KEYWORD_RULES = (
    ("백엔드", ("백엔드", "backend", "server", "서버")),
    ("CS", ("cs", "컴퓨터 과학", "운영체제", "네트워크", "자료구조", "알고리즘")),
    ("DB", ("db", "database", "데이터베이스", "sql")),
    ("Java", ("java",)),
    ("Spring", ("spring", "spring boot", "스프링")),
    ("MySQL", ("mysql",)),
    ("JPA", ("jpa",)),
    ("Redis", ("redis", "레디스", "캐시", "cache")),
    ("Docker", ("docker", "도커")),
    ("API", ("api",)),
    ("JWT", ("jwt",)),
    ("트랜잭션", ("트랜잭션", "transaction")),
    ("인덱스", ("인덱스", "index")),
    ("REST", ("rest", "restful")),
    ("인증", ("인증", "인가", "authentication", "authorization", "auth")),
    ("배포", ("배포", "deploy", "deployment", "ci/cd")),
)


class Command(BaseCommand):
    help = "Backfill missing QuestionBankItem metadata without deleting or reloading rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually update missing metadata. Default is dry-run.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview metadata updates without modifying the database. This is the default.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum rows to update in apply mode. Dry-run still reports the full scope.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        limit = options.get("limit")

        stats, updates, duplicate_groups = self._scan(limit=limit)
        self._print_report(stats, duplicate_groups, apply, limit)

        if not apply:
            self.stdout.write(self.style.WARNING("DRY-RUN: no database changes were made."))
            return

        if not updates:
            self.stdout.write(self.style.SUCCESS("No metadata rows need updates."))
            return

        with transaction.atomic():
            QuestionBankItem.objects.bulk_update(
                updates,
                ["question_hash", "source_ref", "keywords"],
                batch_size=500,
            )
        self.stdout.write(self.style.SUCCESS(f"Updated {len(updates)} question bank rows."))

    def _scan(self, limit=None):
        stats = {
            "total": 0,
            "question_hash_missing": 0,
            "source_ref_missing": 0,
            "keywords_empty": 0,
            "keywords_extractable": 0,
            "rows_with_any_update": 0,
        }
        updates = []
        seen_questions = defaultdict(list)

        queryset = QuestionBankItem.objects.all().only(
            "id",
            "question_text",
            "question_hash",
            "source_file",
            "source_ref",
            "keywords",
        )

        for item in queryset.iterator(chunk_size=1000):
            stats["total"] += 1
            normalized = self._normalize_question(item.question_text)
            if normalized:
                seen_questions[normalized].append(str(item.id))

            changed = False
            if not item.question_hash:
                stats["question_hash_missing"] += 1
                item.question_hash = self._hash_question(item.question_text)
                changed = True

            if not (item.source_ref or "").strip():
                stats["source_ref_missing"] += 1
                item.source_ref = self._build_source_ref(item)
                changed = True

            if not item.keywords:
                stats["keywords_empty"] += 1
                extracted = self._extract_keywords(item.question_text)
                if extracted:
                    stats["keywords_extractable"] += 1
                    item.keywords = extracted
                    changed = True

            if changed:
                stats["rows_with_any_update"] += 1
                if limit is None or len(updates) < limit:
                    updates.append(item)

        duplicate_groups = {
            question: ids
            for question, ids in seen_questions.items()
            if len(ids) > 1
        }
        stats["duplicate_question_groups"] = len(duplicate_groups)
        stats["duplicate_extra_rows"] = sum(len(ids) - 1 for ids in duplicate_groups.values())
        return stats, updates, duplicate_groups

    def _print_report(self, stats, duplicate_groups, apply, limit):
        mode = "APPLY" if apply else "DRY-RUN"
        self.stdout.write(f"mode: {mode}")
        if limit is not None:
            self.stdout.write(f"limit: {limit}")
        self.stdout.write(f"total_rows: {stats['total']}")
        self.stdout.write(f"question_hash_missing: {stats['question_hash_missing']}")
        self.stdout.write(f"source_ref_missing: {stats['source_ref_missing']}")
        self.stdout.write(f"keywords_empty: {stats['keywords_empty']}")
        self.stdout.write(f"keywords_extractable: {stats['keywords_extractable']}")
        self.stdout.write(f"rows_with_any_update: {stats['rows_with_any_update']}")
        self.stdout.write(f"duplicate_question_groups: {stats['duplicate_question_groups']}")
        self.stdout.write(f"duplicate_extra_rows: {stats['duplicate_extra_rows']}")

        if duplicate_groups:
            self.stdout.write("duplicate_report_sample:")
            for question, ids in list(duplicate_groups.items())[:5]:
                preview = question[:90]
                self.stdout.write(f"- count={len(ids)} question={preview} ids={', '.join(ids[:3])}")
            self.stdout.write("duplicates are report-only; no rows are deleted or deactivated.")

    @staticmethod
    def _hash_question(question_text):
        return hashlib.sha256((question_text or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _build_source_ref(item):
        if item.source_file:
            return Path(item.source_file).stem
        return str(item.id)

    @staticmethod
    def _normalize_question(question_text):
        return " ".join((question_text or "").strip().lower().split())

    @staticmethod
    def _extract_keywords(question_text):
        text = (question_text or "").lower()
        keywords = []
        for keyword, aliases in KEYWORD_RULES:
            if any(alias.lower() in text for alias in aliases):
                keywords.append(keyword)
        return keywords
