"""
Compare OpenAI models for the interview AI chain.

Usage:
python manage.py compare_interview_llm_models
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.interview.services.ai_chain_openai_engine import (
    AIChainOpenAIEngine,
    AIChainOpenAIError,
)


DEFAULT_MODELS = ("gpt-4o", "gpt-4o-mini", "gpt-4.1-mini")
DEFAULT_OUTPUT_PATH = Path("reports") / "llm_model_comparison_result.md"


@dataclass
class ModelComparisonResult:
    model: str
    questions: list[str] = field(default_factory=list)
    followup_question: str = ""
    question_elapsed_seconds: float = 0.0
    followup_elapsed_seconds: float = 0.0
    question_json_parse_success: bool = False
    followup_json_parse_success: bool = False
    error: str = ""

    @property
    def total_elapsed_seconds(self) -> float:
        return self.question_elapsed_seconds + self.followup_elapsed_seconds

    @property
    def has_error(self) -> bool:
        return bool(self.error)

    @property
    def json_parse_success(self) -> bool:
        return self.question_json_parse_success and self.followup_json_parse_success


class Command(BaseCommand):
    help = "Compare OpenAI LLM models for interview question and follow-up generation."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument(
            "--models",
            nargs="+",
            default=list(DEFAULT_MODELS),
            help="Models to compare. Defaults to gpt-4o gpt-4o-mini gpt-4.1-mini.",
        )
        parser.add_argument(
            "--output",
            default=str(DEFAULT_OUTPUT_PATH),
            help="Markdown report output path relative to BASE_DIR, or an absolute path.",
        )

    def handle(self, *args, **options):
        self._validate_real_openai_settings()

        models = options["models"]
        output_path = self._resolve_output_path(options["output"])
        results = []

        for model in models:
            self.stdout.write(f"[compare] Running model: {model}")
            results.append(self._run_model(model))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            self._render_report(results),
            encoding="utf-8",
        )

        self.stdout.write(
            self.style.SUCCESS(f"LLM comparison report saved: {output_path}")
        )

    def _validate_real_openai_settings(self) -> None:
        if not getattr(settings, "OPENAI_API_KEY", ""):
            raise CommandError("OPENAI_API_KEY is required. Set it in .env.")

        engine_name = str(
            getattr(settings, "INTERVIEW_AI_CHAIN_ENGINE", "")
        ).strip().lower()
        if engine_name != "openai":
            raise CommandError(
                "INTERVIEW_AI_CHAIN_ENGINE=openai is required for this comparison."
            )

        if not bool(getattr(settings, "INTERVIEW_AI_OPENAI_ENABLE_REAL_CALL", False)):
            raise CommandError(
                "INTERVIEW_AI_OPENAI_ENABLE_REAL_CALL=True is required. "
                "This command does not use mock fallback."
            )

    def _resolve_output_path(self, raw_path: str) -> Path:
        output_path = Path(raw_path)
        if output_path.is_absolute():
            return output_path
        return Path(settings.BASE_DIR) / output_path

    def _run_model(self, model: str) -> ModelComparisonResult:
        result = ModelComparisonResult(model=model)
        engine = AIChainOpenAIEngine(model=model, enable_real_call=True)

        try:
            started_at = perf_counter()
            question_result = engine.generate_questions(
                self._build_question_generation_payload()
            )
            result.question_elapsed_seconds = perf_counter() - started_at
            result.questions = self._extract_questions(question_result)
            result.question_json_parse_success = len(result.questions) == 3
        except AIChainOpenAIError as exc:
            result.question_elapsed_seconds = perf_counter() - started_at
            result.error = self._append_error(result.error, exc)
            return result
        except Exception as exc:
            result.question_elapsed_seconds = perf_counter() - started_at
            result.error = self._append_error(result.error, exc)
            return result

        try:
            started_at = perf_counter()
            followup_result = engine.generate_followup_question(
                self._build_followup_generation_payload()
            )
            result.followup_elapsed_seconds = perf_counter() - started_at
            result.followup_question = self._extract_followup(followup_result)
            result.followup_json_parse_success = bool(result.followup_question)
        except AIChainOpenAIError as exc:
            result.followup_elapsed_seconds = perf_counter() - started_at
            result.error = self._append_error(result.error, exc)
        except Exception as exc:
            result.followup_elapsed_seconds = perf_counter() - started_at
            result.error = self._append_error(result.error, exc)

        return result

    def _build_question_generation_payload(self) -> dict[str, Any]:
        return {
            "session_id": "llm-model-comparison-session",
            "persona": self._persona(),
            "user_profile": {
                "career_type": "junior",
                "major_type": "computer_science",
                "desired_job": "백엔드 개발자",
            },
            "input_sources": {
                "job_description": {
                    "position": "백엔드 개발자",
                    "original_text": (
                        "Python, Django, REST API, DB 설계, 협업 경험을 "
                        "핵심 역량으로 요구합니다."
                    ),
                    "job_requirements": (
                        "Python/Django 기반 백엔드 개발, REST API 설계 및 구현, "
                        "데이터베이스 설계, 팀 협업 경험"
                    ),
                    "keywords": ["Python", "Django", "REST API", "DB 설계", "협업"],
                },
                "resume": {
                    "original_text": (
                        "Django 기반 API 구현, AI 모의면접 시스템 개발, "
                        "질문 생성 및 꼬리질문 생성 로직 구현 경험이 있습니다."
                    ),
                    "skills": [
                        {"skill_name": "Python", "category": "Backend", "level": None},
                        {"skill_name": "Django", "category": "Backend", "level": None},
                        {"skill_name": "REST API", "category": "Backend", "level": None},
                    ],
                    "projects": [
                        {
                            "project_name": "AI 모의면접 시스템",
                            "description": (
                                "Django 기반 API와 AI 면접 질문 생성 및 "
                                "꼬리질문 생성 로직을 구현했습니다."
                            ),
                            "contribution": (
                                "질문 생성 chain, 답변 기반 꼬리질문 생성 로직, "
                                "텍스트 답변 테스트 흐름을 구현했습니다."
                            ),
                        }
                    ],
                },
            },
            "generation_options": {
                "question_count": 3,
                "allow_multiple_source_tags": True,
                "include_source_text_excerpt": True,
            },
        }

    def _build_followup_generation_payload(self) -> dict[str, Any]:
        return {
            "session_id": "llm-model-comparison-session",
            "parent_question": {
                "question_id": "llm-comparison-parent-question",
                "question_text": (
                    "Django 기반 API 구현과 AI 모의면접 시스템 개발에서 "
                    "본인이 맡은 역할과 기술적 의사결정을 설명해주세요."
                ),
                "question_type": "main",
                "source_tags": [
                    {
                        "source_type": "resume",
                        "source_label": "이력서/프로젝트",
                        "source_text_excerpt": (
                            "Django 기반 API 구현, AI 모의면접 시스템 개발, "
                            "질문 생성 및 꼬리질문 생성 로직 구현"
                        ),
                    },
                    {
                        "source_type": "jd",
                        "source_label": "JD",
                        "source_text_excerpt": (
                            "Python, Django, REST API, DB 설계, 협업 경험"
                        ),
                    },
                ],
            },
            "answer": {
                "answer_id": "llm-comparison-answer",
                "answer_text": (
                    "제가 프로젝트에서 데이터를 수집하고 분석해서 결과를 정리했습니다. "
                    "Django를 사용했고, 팀원들과 협업해서 기능을 구현했습니다."
                ),
            },
            "selected_weakness_tag": {
                "answer_weakness_tag_id": "llm-comparison-weakness",
                "weakness_tag_id": "ABSTRACT_ANSWER",
                "tag_name": "ABSTRACT_ANSWER",
                "reason": (
                    "답변이 추상적이며 구체적인 역할, 의사결정, 결과를 더 확인해야 합니다."
                ),
            },
            "persona": self._persona(),
            "prompt_version_id": None,
            "conversation_context": {
                "previous_question_count": 3,
                "previous_followup_count_for_parent": 0,
            },
        }

    def _persona(self) -> dict[str, Any]:
        return {
            "persona_id": 2,
            "persona_type": "practical",
            "name": "실무 면접관",
            "description": (
                "프로젝트 경험, 기술 선택 이유, 문제 해결 과정, 협업 방식을 "
                "실무 관점에서 구체적으로 확인하는 면접관"
            ),
        }

    def _extract_questions(self, result: dict[str, Any]) -> list[str]:
        questions = []
        for question in result.get("questions", [])[:3]:
            if isinstance(question, dict):
                text = str(question.get("question_text", "")).strip()
                if text:
                    questions.append(text)
        return questions

    def _extract_followup(self, result: dict[str, Any]) -> str:
        followup_question = result.get("followup_question", {})
        if not isinstance(followup_question, dict):
            return ""
        return str(followup_question.get("question_text", "")).strip()

    def _render_report(self, results: list[ModelComparisonResult]) -> str:
        generated_at = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S %Z")
        lines = [
            "# LLM Model Comparison Result",
            "",
            f"- Generated at: {generated_at}",
            "- Chain engine: openai",
            "- Real OpenAI call: True",
            "- Mock fallback: disabled by command-level real-call validation and direct engine injection",
            "- Comparison rule: only the model name changes; input data, persona, parent question, and user answer stay fixed",
            "- DB schema changes: none",
            "- Persona: practical",
            "- Test target job: 백엔드 개발자",
            "- JD keywords: Python, Django, REST API, DB 설계, 협업 경험",
            "- Resume/project keywords: Django 기반 API 구현, AI 모의면접 시스템 개발, 질문 생성 및 꼬리질문 생성 로직 구현",
            "- User answer: 제가 프로젝트에서 데이터를 수집하고 분석해서 결과를 정리했습니다. Django를 사용했고, 팀원들과 협업해서 기능을 구현했습니다.",
            "",
            "## Markdown Summary Table",
            "",
            "| 모델명 | 질문 1 | 질문 2 | 질문 3 | 생성된 꼬리질문 | 응답 시간(초) | JSON 파싱 성공 | 오류 여부 | 간단 평가 메모 |",
            "| --- | --- | --- | --- | --- | ---: | --- | --- | --- |",
        ]

        for result in results:
            lines.append(
                "| {model} | {q1} | {q2} | {q3} | {followup} | {elapsed:.2f} | {parse_success} | {error_flag} |  |".format(
                    model=self._md_cell(result.model),
                    q1=self._md_cell(self._question_at(result, 0)),
                    q2=self._md_cell(self._question_at(result, 1)),
                    q3=self._md_cell(self._question_at(result, 2)),
                    followup=self._md_cell(result.followup_question),
                    elapsed=result.total_elapsed_seconds,
                    parse_success="Yes" if result.json_parse_success else "No",
                    error_flag="Yes" if result.has_error else "No",
                )
            )

        lines.extend(
            [
                "",
                "## Detailed Results",
                "",
            ]
        )

        for result in results:
            lines.extend(
                [
                    f"### {result.model}",
                    "",
                    f"- 응답 시간: {result.total_elapsed_seconds:.2f}초",
                    f"- 질문 생성 시간: {result.question_elapsed_seconds:.2f}초",
                    f"- 꼬리질문 생성 시간: {result.followup_elapsed_seconds:.2f}초",
                    f"- JSON 파싱 성공 여부: {'Yes' if result.json_parse_success else 'No'}",
                    f"- 질문 JSON 파싱 성공 여부: {'Yes' if result.question_json_parse_success else 'No'}",
                    f"- 꼬리질문 JSON 파싱 성공 여부: {'Yes' if result.followup_json_parse_success else 'No'}",
                    f"- 오류 여부: {'Yes' if result.has_error else 'No'}",
                    f"- 오류 내용: {result.error or ''}",
                    "- 간단 평가 메모: ",
                    "",
                    "#### Questions",
                    "",
                    f"1. {self._question_at(result, 0)}",
                    f"2. {self._question_at(result, 1)}",
                    f"3. {self._question_at(result, 2)}",
                    "",
                    "#### Follow-up Question",
                    "",
                    result.followup_question or "",
                    "",
                ]
            )

        return "\n".join(lines)

    def _question_at(self, result: ModelComparisonResult, index: int) -> str:
        if index >= len(result.questions):
            return ""
        return result.questions[index]

    def _append_error(self, current_error: str, exc: Exception) -> str:
        message = f"{exc.__class__.__name__}: {exc}"
        if current_error:
            return f"{current_error} / {message}"
        return message

    def _md_cell(self, value: str) -> str:
        return str(value or "").replace("|", "\\|").replace("\n", "<br>")
