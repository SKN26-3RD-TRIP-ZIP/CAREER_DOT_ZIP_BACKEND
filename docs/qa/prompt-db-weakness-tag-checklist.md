# Prompt DB and Weakness Tag QA Checklist

## Scope

This checklist verifies two backend behaviors:

- Interview OpenAI real-call paths use seeded DB prompts instead of hardcoded fallback prompts.
- Follow-up generation persists the selected weakness tag into the existing `WeaknessTag` / `AnswerWeaknessTag` structure and links it to the generated follow-up question.

No step requires forcing an actual OpenAI API call. Use real-call mode only in an environment where API access is intentionally enabled.

## Prerequisites

- Use the target database for QA.
- The project uses snake_case table names:
  - `persona_configs`
  - `prompt_templates`
  - `prompt_versions`
  - `weakness_tags`
  - `interview_answers`
  - `interview_questions`

For local sqlite verification in PowerShell:

```powershell
$env:DATABASE_URL="sqlite:///db.sqlite3"
```

## Seed Default Interview Prompts

Run:

```powershell
python manage.py seed_interview_prompts
```

Expected:

- Command completes successfully.
- Re-running the command does not create duplicate seed rows.
- It updates only the seeded `(persona_type, prompt_type, title, version_number=1)` records.
- It does not truncate or delete prompt tables.

## DB Verification

Open a Django shell:

```powershell
python manage.py shell
```

Run:

```python
from apps.prompt.models import PersonaConfig, PromptTemplate, PromptVersion

PersonaConfig.objects.values("persona_type", "active_template_id")
PromptTemplate.objects.values("persona_config__persona_type", "prompt_type", "title", "default_version_id", "is_active")
PromptVersion.objects.values("template__persona_config__persona_type", "template__prompt_type", "version_number")
```

Expected:

- `coach`, `practical`, and `verifier` exist in `persona_configs`.
- Each persona has 3 active prompt templates:
  - `question_generation`
  - `answer_evaluation`
  - `follow_up_generation`
- Each seeded template has a `default_version_id`.
- Each seeded default version has `version_number=1`.
- `active_template_id` points to that persona's seeded `question_generation` template.

## Runtime Prompt Lookup Verification

Run in Django shell:

```python
from apps.prompt.services import get_runtime_prompt_version

for persona in ["coach", "practical", "verifier"]:
    for prompt_type in ["question_generation", "answer_evaluation", "follow_up_generation"]:
        prompt = get_runtime_prompt_version(persona, prompt_type)
        print(persona, prompt_type, prompt.version_id if prompt else None, bool(prompt and prompt.content))
```

Expected:

- Every line prints a non-null `version_id`.
- Every line prints `True` for content.

## Prompt Metadata QA Without Real OpenAI Call

Use an engine test double or existing tests to validate metadata. The relevant runtime behavior is:

- If DB prompt exists:
  - `prompt_source == "db"`
  - `prompt_version_id` is the used `prompt_versions.id`
- If DB prompt does not exist:
  - `prompt_source == "fallback"`
  - `prompt_version_id is None`

Existing automated coverage:

```powershell
python manage.py test apps.prompt apps.interview.test_ai_chain_openai_engine
```

Expected:

- DB prompt tests assert that the system prompt sent to the fake OpenAI client is the seeded/created DB prompt.
- Fallback tests assert that metadata remains present and explicit.

## Optional Real-Call Smoke Check

Only run this in an environment where OpenAI API access is intentionally enabled.

Environment:

```powershell
$env:INTERVIEW_AI_CHAIN_ENGINE="openai"
$env:INTERVIEW_AI_OPENAI_ENABLE_REAL_CALL="true"
```

Trigger a question generation, answer sufficiency, or follow-up generation flow through the API.

Expected response metadata:

```json
{
  "prompt_version_id": 1,
  "prompt_source": "db"
}
```

The exact `prompt_version_id` depends on the target database.

## Weakness Tag Follow-up Link Verification

Create or use an answer that produces a follow-up question, then call the follow-up endpoint.

Expected database state:

```python
from apps.evaluation.models import AnswerWeaknessTag

mapping = AnswerWeaknessTag.objects.select_related("weakness_tag").get(answer_id="<answer_id>")
print(mapping.weakness_tag.tag_name)
print(mapping.is_selected_for_followup)
print(mapping.used_for)
print(mapping.followup_question_id)
```

Expected:

- One `AnswerWeaknessTag` row exists for the selected weakness tag.
- `is_selected_for_followup == True`
- `used_for == "followup"`
- `followup_question_id` equals the generated row in `interview_questions.id`.

Verify the generated question:

```python
from apps.interview.models import InterviewQuestion

question = InterviewQuestion.objects.get(id=mapping.followup_question_id)
print(question.question_type, question.parent_question_id, question.source_answer_id)
```

Expected:

- `question_type == "follow_up"`
- `parent_question_id` is the original question.
- `source_answer_id` is the answer that triggered the follow-up.

## Duplicate Prevention Check

Call the follow-up endpoint twice for the same answer.

Expected:

- Only one follow-up question is created for the answer.
- Only one `AnswerWeaknessTag` row exists for the same `(answer, weakness_tag)` pair.
- Existing mapping is reused and updated instead of duplicated.

Automated coverage:

```powershell
python manage.py test apps.interview.tests.MVPAnswerFollowupAPITests.test_short_answer_creates_one_linked_followup
python manage.py test apps.interview.tests.MVPAnswerFollowupRealModeAPITests.test_real_mode_followup_reuses_existing_answer_weakness_mapping
```

## Report and Recommendation Visibility

Because the follow-up path writes to the existing `AnswerWeaknessTag` relationship:

- Final report aggregation can read `answer.weakness_mappings`.
- Recommendation aggregation can count `session.answers.prefetch_related("weakness_mappings__weakness_tag")`.

No new model or table is required.
