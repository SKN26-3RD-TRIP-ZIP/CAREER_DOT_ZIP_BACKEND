"""
OpenAI AI Chain 수동 검증 command.

사용 예시:
python manage.py test_interview_openai_chain --chain sufficiency
python manage.py test_interview_openai_chain --chain questions
python manage.py test_interview_openai_chain --chain followup
python manage.py test_interview_openai_chain --chain all

실제 OpenAI 호출:
python manage.py test_interview_openai_chain --chain all --use-real
"""

from __future__ import annotations

import json

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.interview.services.ai_chain_openai_engine import AIChainOpenAIEngine


CHAIN_QUESTIONS = "questions"
CHAIN_SUFFICIENCY = "sufficiency"
CHAIN_FOLLOWUP = "followup"
CHAIN_ALL = "all"


class Command(BaseCommand):
    help = "OpenAI AI Chain engine 수동 검증 command"
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument(
            "--chain",
            choices=[
                CHAIN_QUESTIONS,
                CHAIN_SUFFICIENCY,
                CHAIN_FOLLOWUP,
                CHAIN_ALL,
            ],
            default=CHAIN_ALL,
            help="검증할 chain 선택",
        )
        parser.add_argument(
            "--use-real",
            action="store_true",
            help="실제 OpenAI API 호출을 시도합니다. OPENAI_API_KEY가 필요합니다.",
        )

    def handle(self, *args, **options):
        chain = options["chain"]
        use_real = options["use_real"]

        if use_real and not getattr(settings, "OPENAI_API_KEY", None):
            self.stdout.write(
                self.style.WARNING(
                    "OPENAI_API_KEY가 설정되지 않아 실제 호출을 건너뜁니다. "
                    ".env에 OPENAI_API_KEY를 추가한 뒤 다시 실행해주세요."
                )
            )
            return

        engine = AIChainOpenAIEngine(enable_real_call=use_real)
        result = {}

        if chain in {CHAIN_QUESTIONS, CHAIN_ALL}:
            result[CHAIN_QUESTIONS] = engine.generate_questions(
                self._build_question_generation_payload()
            )

        if chain in {CHAIN_SUFFICIENCY, CHAIN_ALL}:
            result[CHAIN_SUFFICIENCY] = engine.judge_answer_sufficiency(
                self._build_answer_sufficiency_payload()
            )

        if chain in {CHAIN_FOLLOWUP, CHAIN_ALL}:
            result[CHAIN_FOLLOWUP] = engine.generate_followup_question(
                self._build_followup_payload()
            )

        self.stdout.write(
            json.dumps(
                {
                    "engine": "openai",
                    "real_call_enabled": use_real,
                    "chain": chain,
                    "result": result,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    def _build_question_generation_payload(self):
        return {
            "session_id": "manual-session-001",
            "persona": {
                "persona_id": 2,
                "persona_type": "practical",
                "name": "실무 면접관형",
                "description": "프로젝트 경험과 기술 선택 이유를 중심으로 확인하는 면접관",
            },
            "user_profile": {
                "career_type": "신입",
                "major_type": "전공",
                "desired_job": "Backend Developer",
            },
            "input_sources": {
                "job_description": {
                    "position": "Backend Developer",
                    "original_text": "Python, Django, REST API 설계 및 데이터베이스 연동 경험을 요구합니다.",
                    "job_requirements": "Django REST API 설계, SQL 기반 데이터 처리, 협업 경험",
                    "keywords": ["Python", "Django", "REST API", "SQL"],
                },
                "resume": {
                    "original_text": "Django 기반 백엔드 API와 AI Chain 연동 기능을 구현했습니다.",
                    "skills": [
                        {
                            "skill_name": "Python",
                            "category": "Backend",
                            "level": None,
                        },
                        {
                            "skill_name": "Django",
                            "category": "Backend",
                            "level": None,
                        },
                    ],
                    "projects": [
                        {
                            "project_name": "AI 모의면접 시스템",
                            "description": "질문 생성, 답변 판단, 꼬리질문 생성 AI Chain을 설계했습니다.",
                            "contribution": "OpenAI engine 구조와 mock fallback 흐름을 구현했습니다.",
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

    def _build_answer_sufficiency_payload(self):
        return {
            "session_id": "manual-session-001",
            "question": {
                "question_id": "manual-question-001",
                "question_text": "AI 모의면접 시스템에서 본인이 맡은 역할과 기술 선택 이유를 설명해주세요.",
                "question_type": "technical",
                "source_tags": [
                    {
                        "source_type": "resume",
                        "source_label": "이력서 기반",
                        "source_text_excerpt": "AI Chain 구조와 OpenAI engine을 구현",
                    }
                ],
            },
            "answer": {
                "answer_id": "manual-answer-001",
                "answer_text": "제가 AI Chain 구조와 OpenAI engine 연동을 구현했습니다.",
            },
            "persona": {
                "persona_id": 2,
                "persona_type": "practical",
                "name": "실무 면접관형",
                "description": "",
            },
            "prompt_version_id": None,
        }

    def _build_followup_payload(self):
        return {
            "session_id": "manual-session-001",
            "parent_question": {
                "question_id": "manual-question-001",
                "question_text": "AI 모의면접 시스템에서 본인이 맡은 역할과 기술 선택 이유를 설명해주세요.",
                "question_type": "technical",
                "source_tags": [
                    {
                        "source_type": "resume",
                        "source_label": "이력서 기반",
                        "source_text_excerpt": "AI Chain 구조와 OpenAI engine을 구현",
                    }
                ],
            },
            "answer": {
                "answer_id": "manual-answer-001",
                "answer_text": "제가 AI Chain 구조와 OpenAI engine 연동을 구현했습니다.",
            },
            "selected_weakness_tag": {
                "answer_weakness_tag_id": "manual-answer-weakness-001",
                "weakness_tag_id": "manual-weakness-001",
                "tag_name": "기술 선택 이유 부족",
                "reason": "기술 선택 이유와 대안 비교가 부족함",
            },
            "persona": {
                "persona_id": 2,
                "persona_type": "practical",
                "name": "실무 면접관형",
                "description": "",
            },
            "prompt_version_id": None,
            "conversation_context": {
                "previous_question_count": 1,
                "previous_followup_count_for_parent": 0,
            },
        }
