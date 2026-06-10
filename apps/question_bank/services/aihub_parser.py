import json
from pathlib import Path

from .classifier import classify_difficulty, classify_question_type
from .keyword_extractor import extract_keywords


def parse_aihub_file(file_path: str) -> dict | None:
    path = Path(file_path)
    try:
        with path.open(encoding='utf-8') as file:
            payload = json.load(file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    payload = _as_dict(payload)
    dataset = _as_dict(payload.get('dataSet') or payload.get('dataset'))
    info = _as_dict(dataset.get('info'))
    occupation = str(info.get('occupation') or '').strip()
    if occupation.upper() != 'ICT':
        return None

    question = _as_dict(dataset.get('question'))
    question_raw = _as_dict(question.get('raw'))
    question_text = str(question_raw.get('text') or '').strip()
    if not question_text:
        return None

    answer = _as_dict(dataset.get('answer'))
    answer_summary = _as_dict(answer.get('summary'))
    answer_raw = _as_dict(answer.get('raw'))
    answer_example = str(
        answer_summary.get('text') or answer_raw.get('text') or ''
    ).strip()
    metadata = {
        'version': payload.get('version'),
        'occupation': occupation,
        'experience': info.get('experience'),
        'question_word_count': question_raw.get('wordCount'),
        'answer_word_count': answer_raw.get('wordCount'),
    }
    question_type = classify_question_type(question_text, answer_example)

    return {
        'job_category': occupation,
        'question_text': question_text,
        'answer_example': answer_example,
        'question_type': question_type,
        'difficulty': classify_difficulty(question_text, question_type, metadata),
        'keywords': extract_keywords(question_text, answer_example),
        'source': 'aihub',
        'source_file': path.name,
        'source_ref': str(
            payload.get('id')
            or dataset.get('id')
            or info.get('id')
            or path.stem
        ),
        'raw_metadata': metadata,
    }


def _as_dict(value):
    return value if isinstance(value, dict) else {}
