"""
AI 면접 Chain mock engine.

배치 위치:
apps/interview/services/ai_chain_mock_engine.py

역할:
- DB/LLM 연결 전 API 흐름을 검증할 수 있는 deterministic mock 로직 제공
- 추후 OpenAI/Claude engine으로 교체하기 쉽도록 mock 구현을 service wrapper와 분리
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from apps.interview.ai_chain_contracts import (
    DEFAULT_PERSONAS,
    DEFAULT_WEAKNESS_TAG_CANDIDATES,
    NextAction,
    QuestionType,
    SourceType,
)


class AIChainMockEngine:
    """질문 생성, 답변 충족도 판단, 꼬리질문 생성을 담당하는 mock engine."""

    def get_personas(self) -> list[dict[str, Any]]:
        return DEFAULT_PERSONAS

    def get_weakness_tags(self) -> list[dict[str, Any]]:
        return DEFAULT_WEAKNESS_TAG_CANDIDATES

    def generate_questions(self, payload: dict[str, Any]) -> dict[str, Any]:
        """QuestionGenerationChain mock.

        입력 자료가 부족하면 question_bank 기반 fallback 질문을 생성한다.
        """
        session_id = payload.get("session_id")
        input_sources = payload.get("input_sources") or {}
        options = payload.get("generation_options") or {}
        question_count = int(options.get("question_count") or 3)

        source_tags = self._build_source_tags(input_sources)
        fallback_used = not source_tags

        if fallback_used:
            source_tags = [
                {
                    "source_type": SourceType.QUESTION_BANK.value,
                    "source_label": "질문 은행 기반",
                    "source_text_excerpt": "기본 직무 질문",
                }
            ]

        questions: list[dict[str, Any]] = []
        for index in range(1, question_count + 1):
            question_type = self._pick_question_type(index)
            question_text = self._build_question_text(
                index,
                question_type,
                input_sources,
                fallback_used,
            )

            questions.append(
                {
                    "client_question_key": f"q_{index:03d}",
                    "question_text": question_text,
                    "question_type": question_type,
                    "difficulty": None,
                    "order_index": index,
                    "generation_reason": self._build_generation_reason(
                        source_tags,
                        fallback_used,
                    ),
                    "source_tags": (
                        source_tags[:2]
                        if options.get("allow_multiple_source_tags", True)
                        else source_tags[:1]
                    ),
                }
            )

        response: dict[str, Any] = {
            "session_id": session_id,
            "questions": questions,
        }

        if fallback_used:
            response["fallback_used"] = True
            response["fallback_reason"] = "사용자 입력 자료 부족"

        return response

    def judge_answer_sufficiency(self, payload: dict[str, Any]) -> dict[str, Any]:
        """AnswerSufficiencyChain mock.

        간단한 규칙 기반으로 부족한 답변을 감지한다.
        실제 LLM 연결 전까지 API 계약 검증용으로 사용한다.
        """
        answer = payload.get("answer") or {}
        answer_id = answer.get("answer_id")
        answer_text = (answer.get("answer_text") or "").strip()

        candidates = payload.get("weakness_tag_candidates") or DEFAULT_WEAKNESS_TAG_CANDIDATES
        weakness_results = self._detect_weakness_tags(answer_text, candidates)

        if not weakness_results:
            return {
                "answer_id": answer_id,
                "is_sufficient": True,
                "sufficiency_reason": "답변이 질문 의도에 충분히 부합하거나 추가 확인할 약점 태그가 감지되지 않음",
                "answer_weakness_tags": [],
                "selected_weakness_tag": None,
                "should_generate_followup": False,
                "next_action": NextAction.NEXT_QUESTION.value,
            }

        selected = weakness_results[0]
        return {
            "answer_id": answer_id,
            "is_sufficient": False,
            "sufficiency_reason": "답변에서 일부 핵심 정보가 부족하여 추가 확인이 필요함",
            "answer_weakness_tags": weakness_results,
            "selected_weakness_tag": {
                "weakness_tag_id": selected["weakness_tag_id"],
                "tag_name": selected["tag_name"],
                "reason": selected["reason"],
            },
            "should_generate_followup": True,
            "next_action": NextAction.GENERATE_FOLLOWUP.value,
        }

    def generate_followup_question(self, payload: dict[str, Any]) -> dict[str, Any]:
        """FollowUpQuestionChain mock."""
        session_id = payload.get("session_id")
        parent_question = payload.get("parent_question") or {}
        answer = payload.get("answer") or {}
        selected_tag = payload.get("selected_weakness_tag") or {}
        context = payload.get("conversation_context") or {}

        previous_question_count = int(context.get("previous_question_count") or 1)
        previous_followup_count = int(context.get("previous_followup_count_for_parent") or 0)
        order_index = previous_question_count + previous_followup_count + 1

        tag_name = selected_tag.get("tag_name") or "답변 구체성 부족"
        question_text = self._build_followup_text(tag_name)

        return {
            "session_id": session_id,
            "followup_question": {
                "parent_question_id": parent_question.get("question_id"),
                "generated_from_answer_id": answer.get("answer_id"),
                "answer_weakness_tag_id": selected_tag.get("answer_weakness_tag_id"),
                "question_text": question_text,
                "question_type": parent_question.get("question_type") or QuestionType.JOB.value,
                "difficulty": None,
                "order_index": order_index,
                "generation_reason": f"{tag_name} 트리거 태그를 기준으로 생성됨",
            },
        }

    def generate_followup_mock(self, payload: dict[str, Any]) -> dict[str, Any]:
        """답변 충족도 판단 → 꼬리질문 생성까지 한 번에 검증하는 mock API용 service."""
        answer = payload.get("answer") or {}

        sufficiency_payload = {
            "session_id": payload.get("session_id"),
            "question": payload.get("question"),
            "answer": answer,
            "persona": payload.get("persona"),
            "prompt_version_id": payload.get("prompt_version_id"),
            "weakness_tag_candidates": (
                payload.get("weakness_tag_candidates") or DEFAULT_WEAKNESS_TAG_CANDIDATES
            ),
        }
        sufficiency = self.judge_answer_sufficiency(sufficiency_payload)

        if sufficiency["next_action"] == NextAction.NEXT_QUESTION.value:
            return {
                "answer_id": answer.get("answer_id"),
                "next_action": NextAction.NEXT_QUESTION.value,
                "sufficiency": sufficiency,
                "followup_question": None,
            }

        selected = sufficiency["selected_weakness_tag"] or {}
        selected_with_generated_id = {
            **selected,
            "answer_weakness_tag_id": str(uuid4()),
        }

        followup_payload = {
            "session_id": payload.get("session_id"),
            "parent_question": payload.get("question"),
            "answer": answer,
            "selected_weakness_tag": selected_with_generated_id,
            "persona": payload.get("persona"),
            "prompt_version_id": payload.get("prompt_version_id"),
            "conversation_context": (
                payload.get("conversation_context")
                or {
                    "previous_question_count": 1,
                    "previous_followup_count_for_parent": 0,
                }
            ),
        }
        followup = self.generate_followup_question(followup_payload)

        followup_question = {
            "question_id": str(uuid4()),
            **followup["followup_question"],
        }

        return {
            "answer_id": answer.get("answer_id"),
            "next_action": NextAction.GENERATE_FOLLOWUP.value,
            "sufficiency": sufficiency,
            "followup_question": followup_question,
        }

    def _build_source_tags(self, input_sources: dict[str, Any]) -> list[dict[str, Any]]:
        tags: list[dict[str, Any]] = []

        jd = input_sources.get("job_description") or {}
        if jd:
            excerpt = (
                jd.get("job_requirements")
                or jd.get("original_text")
                or ", ".join(jd.get("keywords") or [])
            )
            tags.append(
                {
                    "source_type": SourceType.JD.value,
                    "source_label": "JD 기반",
                    "source_text_excerpt": self._shorten(excerpt),
                }
            )

        resume = input_sources.get("resume") or {}
        if resume:
            projects = resume.get("projects") or []
            if projects:
                first_project = projects[0]
                excerpt = first_project.get("description") or first_project.get("project_name")
            else:
                skills = resume.get("skills") or []
                excerpt = ", ".join(
                    [
                        skill.get("skill_name", "")
                        for skill in skills
                        if isinstance(skill, dict)
                    ]
                )
            tags.append(
                {
                    "source_type": SourceType.RESUME.value,
                    "source_label": "이력서 기반",
                    "source_text_excerpt": self._shorten(excerpt),
                }
            )

        cover_letter = input_sources.get("cover_letter") or {}
        items = cover_letter.get("items") or []
        if items:
            first_item = items[0]
            tags.append(
                {
                    "source_type": SourceType.COVER_LETTER.value,
                    "source_label": "자기소개서 기반",
                    "source_text_excerpt": self._shorten(
                        first_item.get("answer_text") or first_item.get("question")
                    ),
                }
            )

        project_experiences = input_sources.get("project_experiences") or []
        if project_experiences:
            first_project = project_experiences[0]
            tags.append(
                {
                    "source_type": SourceType.PROJECT_EXPERIENCE.value,
                    "source_label": "프로젝트 경험 기반",
                    "source_text_excerpt": self._shorten(
                        first_project.get("description") or first_project.get("contribution")
                    ),
                }
            )

        question_bank = input_sources.get("question_bank") or []
        if question_bank:
            first_question = question_bank[0]
            tags.append(
                {
                    "source_type": SourceType.QUESTION_BANK.value,
                    "source_label": "질문 은행 기반",
                    "source_text_excerpt": self._shorten(first_question.get("question")),
                }
            )

        return tags

    def _build_question_text(
        self,
        index: int,
        question_type: str,
        input_sources: dict[str, Any],
        fallback_used: bool,
    ) -> str:
        if fallback_used:
            fallback_questions = [
                "지원한 직무와 관련해 가장 자신 있는 경험을 설명해주세요.",
                "최근 프로젝트에서 본인이 맡은 역할과 문제 해결 과정을 설명해주세요.",
                "지원 직무에서 가장 중요하다고 생각하는 역량과 그 이유를 설명해주세요.",
            ]
            return fallback_questions[(index - 1) % len(fallback_questions)]

        jd = input_sources.get("job_description") or {}
        resume = input_sources.get("resume") or {}
        projects = resume.get("projects") or []
        project_name = projects[0].get("project_name") if projects else "대표 프로젝트"
        desired_position = jd.get("position") or "지원 직무"

        if question_type == QuestionType.TECHNICAL.value:
            return f"{project_name}에서 사용한 기술을 선택한 이유와 본인이 직접 기여한 부분을 설명해주세요."

        if question_type == QuestionType.JOB.value:
            return f"{desired_position} 직무 요구사항과 본인의 프로젝트 경험이 어떻게 연결되는지 설명해주세요."

        return "팀 프로젝트에서 의견 충돌이나 어려움이 있었던 상황과 이를 해결한 방식을 설명해주세요."

    def _build_generation_reason(self, source_tags: list[dict[str, Any]], fallback_used: bool) -> str:
        if fallback_used:
            return "사용자 입력 자료가 부족하여 질문 은행 기반 기본 질문을 생성함"

        labels = ", ".join([tag.get("source_label", "") for tag in source_tags])
        return f"{labels} 정보를 바탕으로 면접 질문을 생성함"

    def _pick_question_type(self, index: int) -> str:
        sequence = [
            QuestionType.TECHNICAL.value,
            QuestionType.JOB.value,
            QuestionType.PERSONALITY.value,
        ]
        return sequence[(index - 1) % len(sequence)]

    def _detect_weakness_tags(
        self,
        answer_text: str,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not answer_text:
            return [
                self._make_weakness_result(
                    candidates,
                    tag_name="답변 구체성 부족",
                    reason="답변 내용이 비어 있어 질문 의도를 판단할 수 없음",
                    priority_rank=1,
                    selected=True,
                )
            ]

        weakness_results: list[dict[str, Any]] = []
        normalized = answer_text.replace(" ", "")

        if len(answer_text) < 80:
            weakness_results.append(
                self._make_weakness_result(
                    candidates,
                    tag_name="답변 구체성 부족",
                    reason="답변 길이가 짧고 상황, 행동, 결과가 충분히 드러나지 않음",
                    priority_rank=len(weakness_results) + 1,
                    selected=True,
                )
            )

        contribution_keywords = ["제가", "직접", "담당", "맡", "구현", "설계", "주도", "기여"]
        if not any(keyword in answer_text for keyword in contribution_keywords):
            weakness_results.append(
                self._make_weakness_result(
                    candidates,
                    tag_name="본인 기여도 불명확",
                    reason="프로젝트에서 본인이 직접 수행한 역할과 기여가 명확하지 않음",
                    priority_rank=len(weakness_results) + 1,
                    selected=not weakness_results,
                )
            )

        reason_keywords = ["이유", "선택", "비교", "대안", "때문", "기준"]
        if not any(keyword in normalized for keyword in reason_keywords):
            weakness_results.append(
                self._make_weakness_result(
                    candidates,
                    tag_name="기술 선택 이유 부족",
                    reason="사용한 기술이나 도구를 선택한 이유와 판단 기준이 부족함",
                    priority_rank=len(weakness_results) + 1,
                    selected=not weakness_results,
                )
            )

        # 첫 번째 태그만 꼬리질문 생성 대상으로 선택한다.
        for idx, item in enumerate(weakness_results):
            item["priority_rank"] = idx + 1
            item["is_selected_for_followup"] = idx == 0

        return weakness_results

    def _make_weakness_result(
        self,
        candidates: list[dict[str, Any]],
        tag_name: str,
        reason: str,
        priority_rank: int,
        selected: bool,
    ) -> dict[str, Any]:
        matched = next((candidate for candidate in candidates if candidate.get("tag_name") == tag_name), None)
        if not matched:
            matched = {
                "weakness_tag_id": str(uuid4()),
                "tag_name": tag_name,
                "description": "",
            }

        return {
            "weakness_tag_id": matched.get("weakness_tag_id"),
            "tag_name": matched.get("tag_name"),
            "reason": reason,
            "priority_rank": priority_rank,
            "is_selected_for_followup": selected,
        }

    def _build_followup_text(self, tag_name: str) -> str:
        if tag_name == "본인 기여도 불명확":
            return "방금 답변에서 언급한 작업 중 본인이 직접 설계하거나 주도한 부분은 무엇이었나요?"

        if tag_name == "기술 선택 이유 부족":
            return "그 기술을 선택한 이유를 다른 대안과 비교해서 설명해주실 수 있나요?"

        if tag_name == "직무 연관성 부족":
            return "방금 경험이 지원 직무의 어떤 요구 역량과 연결된다고 생각하시나요?"

        return "방금 답변에서 상황, 본인의 행동, 결과를 조금 더 구체적으로 설명해주실 수 있나요?"

    def _shorten(self, text: Any, limit: int = 120) -> str:
        if text is None:
            return ""
        value = str(text).strip()
        return value if len(value) <= limit else value[: limit - 3] + "..."
