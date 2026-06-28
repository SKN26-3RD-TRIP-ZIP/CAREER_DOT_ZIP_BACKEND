# Interview API Surfaces

The interview app currently exposes two active API contracts. Both must remain
available until frontend and other consumers agree on one canonical API.

## Nested REST API

- Code: `apps/interview/views.py`, `apps/interview/serializers.py`
- URL prefix: `/api/v1/interviews/`
- Shape: session-oriented nested resources
- Provides turns, source tags, evaluation data, progress, session completion,
  and detailed question, answer, and follow-up responses
- Answer policy: preserves the existing update-capable `update_or_create` flow

## Flat MVP API

- Code: `apps/interview/mvp_views.py`, `apps/interview/mvp_serializers.py`
- URL prefix: `/api/v1/`
- Shape: compact endpoints such as `/sessions`, `/answers`, and
  `/answers/{answer_id}/followup`
- Provides frontend-oriented compact responses, status/persona aliases, STT,
  TTS, and MVP follow-up actions
- Answer policy: duplicate answers are rejected through `AnswerService`

## Field Meanings

- `interview_type`: question content mix (`technical`, `personality`,
  `comprehensive`)
- `interview_mode`: interaction channel (`text`, `voice`)
- `question_type`: structural turn role (`main`, `follow_up`)
- `question_category`: content class (`technical`, `personality`, `general`)

These fields are not interchangeable and must not be merged.

## Compatibility Policy

- Treat both API surfaces as active contracts.
- Do not remove, merge, or rename either surface before selecting a canonical
  API with frontend, evaluation, report, and QA consumers.
- Preserve response keys, aliases, URL paths, and answer persistence behavior.
- Shared helpers may be extracted only when both public contracts remain
  unchanged.
- `FollowupGenerator._build_sufficiency_payload()` remains as a compatibility
  wrapper. New integrations should use
  `InterviewAIChainService.evaluate_answer_sufficiency(answer)`.
