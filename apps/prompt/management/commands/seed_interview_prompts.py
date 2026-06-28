from django.core.management.base import BaseCommand
from django.db import transaction

from apps.prompt.models import PersonaConfig, PromptTemplate, PromptVersion


PERSONA_SEEDS = {
    "coach": {
        "description": "지원자가 답변을 명확하게 구조화하도록 돕는 코치형 면접관입니다.",
        "persona_instruction": (
            "따뜻하고 성장 중심적인 코치형 톤을 사용하세요. 지원자가 상황, 행동, 결과, "
            "배운 점을 명확히 드러낼 수 있도록 구체적인 질문을 하세요."
        ),
    },
    "practical": {
        "description": "직무 관련성과 실행 경험을 중심으로 확인하는 실무형 면접관입니다.",
        "persona_instruction": (
            "차분한 실무형 면접관 톤을 사용하세요. 지원자의 실제 역할, 구현 판단, "
            "트레이드오프, 측정 가능한 결과를 확인하세요."
        ),
    },
    "verifier": {
        "description": "주장의 근거와 개인 기여도를 깊이 검증하는 검증형 면접관입니다.",
        "persona_instruction": (
            "근거 중심의 검증형 면접관 톤을 사용하세요. 주장 근거, 개인 기여도, "
            "기술적 깊이, 직무와의 일관성을 확인하세요."
        ),
    },
}


PROMPT_SEEDS = {
    "question_generation": {
        "title": "기본 면접 질문 생성 프롬프트",
        "content": """당신은 IT 직무 면접 질문을 생성하는 엔진입니다.

페르소나 지시:
{persona_instruction}

반드시 JSON object만 반환하세요.
최상위 필드:
- session_id
- questions

questions 배열의 각 항목에는 다음 key를 포함해야 합니다:
- client_question_key
- question_text
- question_type
- question_category
- expected_technical_keywords
- difficulty
- order_index
- generation_reason
- source_tags

규칙:
- question_type은 반드시 "main"이어야 합니다.
- question_category는 technical, personality, general 중 하나여야 합니다.
- technical 질문에는 expected_technical_keywords에 기대하는 핵심 기술 개념/키워드를 쉼표로 구분해 넣으세요.
- expected_technical_keywords는 문장형 모범답안이 아니라 핵심 키워드/개념 나열이어야 합니다.
- personality 또는 general 질문에는 expected_technical_keywords를 빈 문자열로 두세요.
- generation_options.question_category_plan이 제공되면 해당 순서와 비율을 우선 따르세요.
- 채용공고, 이력서, 자기소개서, 프로젝트 경험, analysis에서 생성된 예상 질문, 사용자 프로필을 근거로 질문을 만드세요.
- source_tags에는 source_type, source_label, source_text_excerpt를 가진 object를 넣으세요.
- source_type은 jd, resume, cover_letter, project_experience, analysis_question, general 중 하나여야 합니다.
- 구체적인 입력 자료가 있으면 general 질문만으로 구성하지 마세요.
- 사용자가 제공한 맥락이 명확히 영어뿐인 경우를 제외하고 자연스러운 한국어 면접 질문을 작성하세요.
""",
    },
    "answer_evaluation": {
        "title": "기본 답변 충분성 평가 프롬프트",
        "content": """당신은 IT 직무 면접 답변의 충분성을 평가하는 엔진입니다.

페르소나 지시:
{persona_instruction}

반드시 JSON object만 반환하세요.
최상위 필드:
- answer_id
- is_sufficient
- sufficiency_reason
- answer_weakness_tags
- selected_weakness_tag
- should_generate_followup
- next_action

규칙:
- next_action은 반드시 NEXT_QUESTION 또는 GENERATE_FOLLOWUP 중 하나여야 합니다.
- 약점 태그를 선택할 때는 제공된 weakness_tag_candidates를 우선 사용하세요.
- 꼬리질문이 필요하다면 selected_weakness_tag는 생성된 follow-up trigger tag 중 하나여야 합니다.
- 답변이 너무 짧거나, 추상적이거나, 질문과 어긋나거나, 이유/결과/역할이 빠졌거나, JD와의 연결이 약하거나, 기술적 깊이가 부족하면 꼬리질문이 필요합니다.
- 구체적 상황, 본인 행동, 판단 근거, 기여도, 결과, 직무 관련성이 충분히 드러난 경우에만 다음 질문으로 진행하세요.
""",
    },
    "follow_up_generation": {
        "title": "기본 꼬리질문 생성 프롬프트",
        "content": """당신은 selected_weakness_tag를 바탕으로 꼬리질문 1개를 생성하는 IT 직무 면접관입니다.

페르소나 지시:
{persona_instruction}

반드시 JSON object만 반환하세요.
최상위 필드:
- session_id
- followup_question

followup_question에는 다음 key를 포함해야 합니다:
- parent_question_id
- generated_from_answer_id
- answer_weakness_tag_id
- question_text
- question_type
- difficulty
- order_index
- generation_reason

규칙:
- 자연스러운 한국어 꼬리질문을 정확히 1개만 생성하세요.
- 질문은 selected_weakness_tag가 가리키는 부족한 지점을 직접 확인해야 합니다.
- 원 질문을 반복하지 마세요.
- 면접 상황에 맞고, 구체적이며, 검증 가능한 질문으로 작성하세요.
""",
    },
}


class Command(BaseCommand):
    help = "Seed idempotent default DB prompts for interview OpenAI chains."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dedupe",
            action="store_true",
            help=(
                "Deactivate duplicate seed-scope PromptTemplate rows for the same "
                "persona_config and prompt_type after seeding."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        created_personas = 0
        updated_personas = 0
        created_templates = 0
        updated_templates = 0
        created_versions = 0
        updated_versions = 0
        deactivated_duplicates = 0

        for persona_type, persona_payload in PERSONA_SEEDS.items():
            persona, persona_created = PersonaConfig.objects.update_or_create(
                persona_type=persona_type,
                defaults={
                    "description": persona_payload["description"],
                    "is_active": True,
                },
            )
            if persona_created:
                created_personas += 1
            else:
                updated_personas += 1

            active_question_template = None
            for prompt_type, prompt_payload in PROMPT_SEEDS.items():
                title = f"{prompt_payload['title']} ({persona_type})"
                template, template_created = self._get_or_create_seed_template(
                    persona=persona,
                    prompt_type=prompt_type,
                    title=title,
                )
                if template_created:
                    created_templates += 1
                else:
                    updated_templates += 1

                content = prompt_payload["content"].format(
                    persona_instruction=persona_payload["persona_instruction"],
                ).strip()
                version, version_created = PromptVersion.objects.update_or_create(
                    template=template,
                    version_number=1,
                    defaults={
                        "content": content,
                        "change_note": "Seeded default interview prompt.",
                    },
                )
                if version_created:
                    created_versions += 1
                else:
                    updated_versions += 1

                if template.default_version_id != version.id:
                    template.default_version = version
                    template.save(update_fields=("default_version", "updated_at"))

                if prompt_type == "question_generation":
                    active_question_template = template

                if options["dedupe"]:
                    deactivated_duplicates += self._deactivate_duplicate_templates(
                        persona=persona,
                        prompt_type=prompt_type,
                        keep_template=template,
                    )

            if active_question_template and persona.active_template_id != active_question_template.id:
                persona.active_template = active_question_template
                persona.save(update_fields=("active_template", "updated_at"))

        self.stdout.write(
            self.style.SUCCESS(
                "Interview prompts seeded: "
                f"personas created={created_personas}, updated={updated_personas}; "
                f"templates created={created_templates}, updated={updated_templates}; "
                f"versions created={created_versions}, updated={updated_versions}; "
                f"duplicate templates deactivated={deactivated_duplicates}."
            )
        )

    def _get_or_create_seed_template(self, *, persona, prompt_type, title):
        candidates = list(
            PromptTemplate.objects.filter(
                persona_config=persona,
                prompt_type=prompt_type,
            ).order_by("id")
        )

        template = self._select_seed_template(
            persona=persona,
            prompt_type=prompt_type,
            title=title,
            candidates=candidates,
        )
        if template is not None:
            template.title = title
            template.is_active = True
            template.save(update_fields=("title", "is_active", "updated_at"))
            return template, False

        return PromptTemplate.objects.create(
            persona_config=persona,
            prompt_type=prompt_type,
            title=title,
            is_active=True,
        ), True

    def _select_seed_template(self, *, persona, prompt_type, title, candidates):
        if not candidates:
            return None

        if (
            prompt_type == "question_generation"
            and persona.active_template_id
        ):
            for template in candidates:
                if template.id == persona.active_template_id:
                    return template

        for template in candidates:
            if template.title == title:
                return template

        for template in candidates:
            if template.is_active and template.default_version_id:
                return template

        for template in candidates:
            if template.is_active:
                return template

        return candidates[0]

    def _deactivate_duplicate_templates(self, *, persona, prompt_type, keep_template):
        duplicate_ids = list(
            PromptTemplate.objects.filter(
                persona_config=persona,
                prompt_type=prompt_type,
            )
            .exclude(id=keep_template.id)
            .filter(is_active=True)
            .values_list("id", flat=True)
        )
        if not duplicate_ids:
            return 0

        return PromptTemplate.objects.filter(id__in=duplicate_ids).update(is_active=False)
