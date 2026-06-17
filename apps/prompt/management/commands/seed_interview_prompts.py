from django.core.management.base import BaseCommand
from django.db import transaction

from apps.prompt.models import PersonaConfig, PromptTemplate, PromptVersion


PERSONA_SEEDS = {
    "coach": {
        "description": "Supportive interviewer that helps candidates structure answers clearly.",
        "persona_instruction": (
            "Use a warm coaching tone. Ask clear, specific interview questions and "
            "help the candidate reveal situation, action, result, and learning."
        ),
    },
    "practical": {
        "description": "Practical interviewer focused on job relevance and execution details.",
        "persona_instruction": (
            "Use a calm practical interviewer tone. Verify the candidate's actual role, "
            "implementation decisions, trade-offs, and measurable results."
        ),
    },
    "verifier": {
        "description": "Evidence-focused interviewer that checks claims and personal contribution.",
        "persona_instruction": (
            "Use an evidence-focused interviewer tone. Check the basis of claims, "
            "personal contribution, technical depth, and consistency with the job."
        ),
    },
}


PROMPT_SEEDS = {
    "question_generation": {
        "title": "Seed Interview Question Generation",
        "content": """You are an IT job interview question generation engine.

Persona instruction:
{persona_instruction}

Return only a JSON object.
Top-level fields:
- session_id
- questions

Each item in questions must include:
- client_question_key
- question_text
- question_type
- difficulty
- order_index
- generation_reason
- source_tags

Rules:
- question_type must be "main".
- Base questions on the provided job description, resume, cover letter, project experience, prepared questions, or user profile.
- source_tags must contain objects with source_type, source_label, and source_text_excerpt.
- source_type must be one of jd, resume, cover_letter, project_experience, general.
- If specific input sources exist, do not rely only on general questions.
- Ask natural Korean interview questions unless the user-provided context is clearly English-only.
""",
    },
    "answer_evaluation": {
        "title": "Seed Interview Answer Evaluation",
        "content": """You are an IT job interview answer sufficiency evaluation engine.

Persona instruction:
{persona_instruction}

Return only a JSON object.
Top-level fields:
- answer_id
- is_sufficient
- sufficiency_reason
- answer_weakness_tags
- selected_weakness_tag
- should_generate_followup
- next_action

Rules:
- next_action must be either NEXT_QUESTION or GENERATE_FOLLOWUP.
- Use the provided weakness_tag_candidates when selecting weakness tags.
- selected_weakness_tag must be one of the generated follow-up trigger tags when a follow-up is needed.
- Generate a follow-up when the answer is too short, abstract, off topic, missing reason/result/role, weakly linked to the JD, or too shallow technically.
- Continue to the next question only when the answer includes concrete situation, personal action, rationale, contribution, result, and job relevance.
""",
    },
    "follow_up_generation": {
        "title": "Seed Interview Follow-up Generation",
        "content": """You are an IT job interviewer generating one follow-up question from a selected weakness tag.

Persona instruction:
{persona_instruction}

Return only a JSON object.
Top-level fields:
- session_id
- followup_question

followup_question must include:
- parent_question_id
- generated_from_answer_id
- answer_weakness_tag_id
- question_text
- question_type
- difficulty
- order_index
- generation_reason

Rules:
- Generate exactly one natural Korean follow-up question.
- The question must directly address selected_weakness_tag.
- Do not repeat the parent question.
- Keep the tone interview-like, specific, and verifiable.
""",
    },
}


class Command(BaseCommand):
    help = "Seed idempotent default DB prompts for interview OpenAI chains."

    @transaction.atomic
    def handle(self, *args, **options):
        created_personas = 0
        updated_personas = 0
        created_templates = 0
        updated_templates = 0
        created_versions = 0
        updated_versions = 0

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
                template, template_created = PromptTemplate.objects.update_or_create(
                    persona_config=persona,
                    prompt_type=prompt_type,
                    title=title,
                    defaults={
                        "is_active": True,
                    },
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

            if active_question_template and persona.active_template_id != active_question_template.id:
                persona.active_template = active_question_template
                persona.save(update_fields=("active_template", "updated_at"))

        self.stdout.write(
            self.style.SUCCESS(
                "Interview prompts seeded: "
                f"personas created={created_personas}, updated={updated_personas}; "
                f"templates created={created_templates}, updated={updated_templates}; "
                f"versions created={created_versions}, updated={updated_versions}."
            )
        )
