#!/usr/bin/env python
"""Read-only data query CLI for the Career.zip backend.

This script intentionally performs SELECT-only Django ORM queries, plus an
optional read-only Pinecone describe_index_stats call for ``pinecone_stats``.
It does not create, update, delete, migrate, or modify project settings.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

SECRET_FIELD_RE = re.compile(
    r"(password|token|secret|api[_-]?key|refresh|access|authorization)",
    re.IGNORECASE,
)
PII_EXACT_FIELDS = {"email", "phone", "address", "name"}
PII_NAME_FIELDS = {
    "user_name",
    "person_name",
    "applicant_name",
    "candidate_name",
    "member_name",
    "student_name",
}
PREVIEW_FIELDS = {
    "original_text",
    "answer_text",
    "stt_text",
    "question_text",
    "description",
    "summary",
    "source_ref",
    "source_reference",
    "job_requirements",
    "keywords",
    "extracted_keywords",
}
PREVIEW_LIMIT = 120


@dataclass(frozen=True)
class ModelConfig:
    label: str
    import_path: str
    default_columns: tuple[str, ...]
    user_filter: str | None = None
    status_field: str | None = None
    source_field: str | None = None
    job_category_field: str | None = None
    question_type_field: str | None = None
    difficulty_field: str | None = None
    default_search_fields: tuple[str, ...] = ()
    default_sort: str = "id"


MODEL_CONFIGS: dict[str, ModelConfig] = {
    "jd": ModelConfig(
        "jd",
        "apps.input.models.JobDescription",
        ("id", "user_id", "company_name", "position", "analysis_status", "input_method", "source_url", "created_at"),
        user_filter="user_id",
        status_field="analysis_status",
        default_search_fields=("company_name", "position", "original_text", "job_requirements", "keywords"),
        default_sort="created_at",
    ),
    "resume": ModelConfig(
        "resume",
        "apps.input.models.ResumeMaster",
        ("id", "user_id", "name", "email", "phone", "github_url", "is_active", "created_at"),
        user_filter="user_id",
        default_search_fields=("name", "email", "original_text", "extracted_keywords"),
        default_sort="created_at",
    ),
    "cover_letter": ModelConfig(
        "cover_letter",
        "apps.input.models.CoverLetter",
        ("id", "user_id", "jd_id", "title", "company_name", "is_active", "created_at"),
        user_filter="user_id",
        default_search_fields=("title", "company_name"),
        default_sort="created_at",
    ),
    "project": ModelConfig(
        "project",
        "apps.input.models.ProjectExperience",
        ("id", "user_id", "project_name", "tech_stack", "github_url", "created_at"),
        user_filter="user_id",
        default_search_fields=("project_name", "description", "contribution", "tech_stack"),
        default_sort="created_at",
    ),
    "analysis_session": ModelConfig(
        "analysis_session",
        "apps.analysis.models.AnalysisSession",
        ("id", "user_id", "jd_id", "resume_id", "cover_letter_id", "job_role", "company_name", "status", "career_level", "created_at"),
        user_filter="user_id",
        status_field="status",
        default_search_fields=("job_role", "company_name", "jd_text", "resume_text", "cover_letter_text"),
        default_sort="created_at",
    ),
    "interview_session": ModelConfig(
        "interview_session",
        "apps.interview.models.InterviewSession",
        ("id", "user_id", "jd_id", "resume_id", "cover_letter_id", "interview_type", "persona", "status", "interview_mode", "created_at"),
        user_filter="user_id",
        status_field="status",
        default_search_fields=("interview_type", "persona", "status"),
        default_sort="created_at",
    ),
    "generated_question": ModelConfig(
        "generated_question",
        "apps.analysis.models.GeneratedQuestion",
        ("id", "jd_analysis_id", "question_type", "source", "question_text", "order", "is_used"),
        user_filter="jd_analysis__user_id",
        source_field="source",
        question_type_field="question_type",
        default_search_fields=("question_text", "source_ref"),
        default_sort="order",
    ),
    "interview_question": ModelConfig(
        "interview_question",
        "apps.interview.models.InterviewQuestion",
        ("id", "session_id", "order_index", "question_type", "question_category", "difficulty", "source_type", "question_text", "created_at"),
        user_filter="session__user_id",
        source_field="source_type",
        question_type_field="question_type",
        difficulty_field="difficulty",
        default_search_fields=("question_text", "source_reference"),
        default_sort="order_index",
    ),
    "question_bank": ModelConfig(
        "question_bank",
        "apps.question_bank.models.QuestionBankItem",
        ("id", "job_category", "question_type", "difficulty", "source", "source_file", "source_ref", "is_active", "is_embedded", "question_text"),
        source_field="source",
        job_category_field="job_category",
        question_type_field="question_type",
        difficulty_field="difficulty",
        default_search_fields=("question_text", "answer_example", "keywords", "source_file", "source_ref"),
        default_sort="created_at",
    ),
    "answer": ModelConfig(
        "answer",
        "apps.interview.models.InterviewAnswer",
        ("id", "session_id", "question_id", "answer_source", "answer_text", "speech_duration", "created_at"),
        user_filter="session__user_id",
        source_field="answer_source",
        default_search_fields=("answer_text", "stt_text"),
        default_sort="created_at",
    ),
    "evaluation": ModelConfig(
        "evaluation",
        "apps.evaluation.models.Evaluation",
        ("id", "answer_id", "answer_score", "llm_concept_score", "sbert_db_similarity", "sbert_readme_similarity", "evaluated_at"),
        user_filter="answer__session__user_id",
        default_search_fields=("score_detail", "bei_score", "cbi_score"),
        default_sort="evaluated_at",
    ),
    "report": ModelConfig(
        "report",
        "apps.report.models.FinalReport",
        ("id", "session_id", "status", "error_code", "generated_at", "updated_at"),
        user_filter="session__user_id",
        status_field="status",
        default_search_fields=("summary", "error_code"),
        default_sort="generated_at",
    ),
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Career.zip read-only data query CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--model", required=True, choices=sorted([*MODEL_CONFIGS.keys(), "pinecone_stats"]))
    parser.add_argument("--status")
    parser.add_argument("--source")
    parser.add_argument("--job-category")
    parser.add_argument("--question-type")
    parser.add_argument("--difficulty")
    parser.add_argument("--user-id")
    parser.add_argument("--search")
    parser.add_argument("--search-fields", help="Comma-separated field names. Defaults are model-specific.")
    parser.add_argument("--sort-by")
    parser.add_argument("--order", choices=("asc", "desc"), default="desc")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--size", type=int, default=20)
    parser.add_argument("--format", choices=("table", "json", "csv"), default="table")
    parser.add_argument("--export", help="Optional output path for json/csv/table text")
    parser.add_argument("--columns", help="Comma-separated columns. Defaults are model-specific.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.model == "pinecone_stats":
            rows = [query_pinecone_stats()]
            output_rows(rows, args, total_count=len(rows), displayed_count=len(rows), columns=list(rows[0].keys()))
            return 0

        setup_django()
        cfg = MODEL_CONFIGS[args.model]
        model = import_model(cfg.import_path)
        rows, total_count, displayed_count, columns = query_model(model, cfg, args)
        output_rows(rows, args, total_count=total_count, displayed_count=displayed_count, columns=columns)
        return 0
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {sanitize_error(str(exc))}", file=sys.stderr)
        return 1


def setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    # apps.accounts starts APScheduler for generic script entrypoints. This CLI is
    # read-only, so initialize Django with a management-command-like argv shape
    # to avoid scheduler DB writes during AppConfig.ready().
    original_argv = sys.argv[:]
    try:
        sys.argv = ["manage.py", "career_zip_data_query"]
        django.setup()
    finally:
        sys.argv = original_argv


def import_model(import_path: str):
    module_name, class_name = import_path.rsplit(".", 1)
    module = import_module(module_name)
    return getattr(module, class_name)


def query_model(model, cfg: ModelConfig, args: argparse.Namespace):
    validate_pagination(args.page, args.size)
    columns = parse_columns(args.columns, cfg.default_columns)
    validate_columns(model, columns)

    qs = model.objects.all()
    qs = apply_filters(qs, model, cfg, args)
    total_count = qs.count()
    qs = apply_sort(qs, model, cfg, args)
    start = (args.page - 1) * args.size
    end = start + args.size
    page_rows = list(qs[start:end])
    rows = [serialize_object(obj, columns) for obj in page_rows]
    return rows, total_count, len(rows), columns


def apply_filters(qs, model, cfg: ModelConfig, args: argparse.Namespace):
    filter_specs = (
        ("--status", args.status, cfg.status_field),
        ("--source", args.source, cfg.source_field),
        ("--job-category", args.job_category, cfg.job_category_field),
        ("--question-type", args.question_type, cfg.question_type_field),
        ("--difficulty", args.difficulty, cfg.difficulty_field),
        ("--user-id", args.user_id, cfg.user_filter),
    )
    for option_name, value, field_name in filter_specs:
        if value is None:
            continue
        if not field_name:
            raise ValueError(f"{option_name} is not supported for model '{cfg.label}'.")
        qs = qs.filter(**{field_name: value})

    if args.search:
        search_fields = parse_columns(args.search_fields, cfg.default_search_fields)
        if not search_fields:
            raise ValueError(f"--search is not supported for model '{cfg.label}' without --search-fields.")
        validate_filter_fields(model, search_fields, "--search-fields")
        from django.db.models import Q

        query = Q()
        for field in search_fields:
            query |= Q(**{f"{field}__icontains": args.search})
        qs = qs.filter(query)
    elif args.search_fields:
        raise ValueError("--search-fields requires --search.")

    return qs


def apply_sort(qs, model, cfg: ModelConfig, args: argparse.Namespace):
    sort_by = args.sort_by or cfg.default_sort
    validate_filter_fields(model, [sort_by], "--sort-by")
    direction = "" if args.order == "asc" else "-"
    return qs.order_by(f"{direction}{sort_by}")


def validate_pagination(page: int, size: int) -> None:
    if page < 1:
        raise ValueError("--page must be >= 1.")
    if size < 1 or size > 500:
        raise ValueError("--size must be between 1 and 500.")


def parse_columns(value: str | None, default: tuple[str, ...]) -> list[str]:
    if not value:
        return list(default)
    columns = [part.strip() for part in value.split(",") if part.strip()]
    if not columns:
        raise ValueError("Column list cannot be empty.")
    return columns


def validate_columns(model, columns: list[str]) -> None:
    field_names = concrete_field_names(model)
    unsupported = [column for column in columns if column not in field_names]
    if unsupported:
        raise ValueError(
            f"Unsupported column(s) for {model.__name__}: {', '.join(unsupported)}. "
            f"Use direct model field names only."
        )


def validate_filter_fields(model, fields: list[str], option_name: str) -> None:
    field_names = concrete_field_names(model)
    relation_names = {field.name for field in model._meta.get_fields() if getattr(field, "is_relation", False)}
    invalid = []
    for field in fields:
        first = field.split("__", 1)[0]
        if first not in field_names and first not in relation_names:
            invalid.append(field)
    if invalid:
        raise ValueError(f"Unsupported field(s) for {option_name}: {', '.join(invalid)}.")


def concrete_field_names(model) -> set[str]:
    names = set()
    for field in model._meta.fields:
        names.add(field.name)
        if getattr(field, "attname", None):
            names.add(field.attname)
    return names


def serialize_object(obj: Any, columns: list[str]) -> dict[str, Any]:
    return {column: safe_value(column, getattr(obj, column)) for column in columns}


def safe_value(field_name: str, value: Any) -> Any:
    lowered = field_name.lower()
    if SECRET_FIELD_RE.search(lowered):
        return "[EXCLUDED]"
    if value is None:
        return None
    if should_mask_pii(field_name):
        return mask_pii(field_name, str(value))
    if isinstance(value, (dict, list, tuple)):
        rendered = json.dumps(value, ensure_ascii=False, default=str)
    else:
        rendered = str(value)
    if field_name in PREVIEW_FIELDS or len(rendered) > PREVIEW_LIMIT:
        return preview(rendered)
    return rendered


def should_mask_pii(field_name: str) -> bool:
    lowered = field_name.lower()
    if lowered in PII_EXACT_FIELDS or lowered in PII_NAME_FIELDS:
        return True
    if lowered.endswith("_email") or lowered.endswith("_phone") or lowered.endswith("_address"):
        return True
    if lowered.startswith(("email_", "phone_", "address_")):
        return True
    return False


def mask_pii(field_name: str, value: str) -> str:
    if not value:
        return value
    if "email" in field_name.lower() or "@" in value:
        name, sep, domain = value.partition("@")
        if not sep:
            return mask_middle(value)
        return f"{mask_middle(name)}@{domain}"
    if "phone" in field_name.lower():
        digits = re.sub(r"\D", "", value)
        if len(digits) >= 7:
            return f"{digits[:3]}****{digits[-4:]}"
    return mask_middle(value)


def mask_middle(value: str) -> str:
    if len(value) <= 2:
        return "*" * len(value)
    return f"{value[0]}{'*' * max(len(value) - 2, 1)}{value[-1]}"


def preview(value: str) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= PREVIEW_LIMIT:
        return compact
    return compact[:PREVIEW_LIMIT] + "..."


def query_pinecone_stats() -> dict[str, Any]:
    load_env_file()
    api_key = os.getenv("PINECONE_API_KEY")
    index_name = os.getenv("PINECONE_INDEX_NAME")
    if not api_key:
        raise RuntimeError("PINECONE_API_KEY is not set.")
    if not index_name:
        raise RuntimeError("PINECONE_INDEX_NAME is not set.")

    from pinecone import Pinecone

    try:
        pc = Pinecone(api_key=api_key)
        index_names = pc.list_indexes().names()
        if index_name not in index_names:
            return {
                "pinecone_index_name": index_name,
                "target_index_found": False,
                "total_vector_count": None,
                "namespaces": {},
            }
        stats = pc.Index(index_name).describe_index_stats()
        total = getattr(stats, "total_vector_count", None)
        namespaces = getattr(stats, "namespaces", None) or {}
        namespace_counts = {
            name: getattr(info, "vector_count", None)
            for name, info in namespaces.items()
        }
        return {
            "pinecone_index_name": index_name,
            "target_index_found": True,
            "total_vector_count": total,
            "namespaces": namespace_counts,
        }
    except Exception as exc:
        raise RuntimeError(f"Pinecone read failed: {type(exc).__name__}: {sanitize_error(str(exc))}") from exc


def load_env_file() -> None:
    try:
        from dotenv import load_dotenv

        env_path = Path.cwd() / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except Exception:
        return


def output_rows(
    rows: list[dict[str, Any]],
    args: argparse.Namespace,
    *,
    total_count: int,
    displayed_count: int,
    columns: list[str],
) -> None:
    if args.format == "json":
        payload: Any = {
            "model": args.model,
            "total_count": total_count,
            "displayed_count": displayed_count,
            "page": args.page,
            "size": args.size,
            "results": rows,
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    elif args.format == "csv":
        text = render_csv(rows, columns)
    else:
        text = render_table(rows, columns, total_count, displayed_count, args)

    if args.export:
        Path(args.export).write_text(text, encoding="utf-8", newline="")
    else:
        print(text)


def render_csv(rows: list[dict[str, Any]], columns: list[str]) -> str:
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: csv_cell(row.get(column)) for column in columns})
    return buffer.getvalue()


def csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def render_table(
    rows: list[dict[str, Any]],
    columns: list[str],
    total_count: int,
    displayed_count: int,
    args: argparse.Namespace,
) -> str:
    lines = [
        f"model: {args.model}",
        f"total_count: {total_count}",
        f"displayed_count: {displayed_count}",
        f"page: {args.page}",
        f"size: {args.size}",
    ]
    if not rows:
        lines.append("(no rows)")
        return "\n".join(lines)

    rendered_rows = [
        {column: printable(row.get(column)) for column in columns}
        for row in rows
    ]
    widths = {
        column: min(max(len(column), *(len(row[column]) for row in rendered_rows)), 60)
        for column in columns
    }
    header = " | ".join(column.ljust(widths[column]) for column in columns)
    sep = "-+-".join("-" * widths[column] for column in columns)
    lines.extend([header, sep])
    for row in rendered_rows:
        lines.append(" | ".join(row[column][: widths[column]].ljust(widths[column]) for column in columns))
    return "\n".join(lines)


def printable(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def sanitize_error(message: str) -> str:
    redacted = SECRET_FIELD_RE.sub("[REDACTED_FIELD]", message or "")
    api_key = os.getenv("PINECONE_API_KEY")
    if api_key:
        redacted = redacted.replace(api_key, "[REDACTED]")
    return redacted


if __name__ == "__main__":
    raise SystemExit(main())
