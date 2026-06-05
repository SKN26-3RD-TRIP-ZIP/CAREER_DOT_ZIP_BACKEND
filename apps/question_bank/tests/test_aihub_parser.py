import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.question_bank.services.aihub_parser import parse_aihub_file


class AIHubParserTests(SimpleTestCase):
    def write_payload(self, payload):
        temporary_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_dir.cleanup)
        path = Path(temporary_dir.name) / 'sample.json'
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        return path

    def payload(self, occupation='ICT', question='API를 구현한 경험은?', summary='요약 답변'):
        return {
            'version': '1.0',
            'dataSet': {
                'info': {'occupation': occupation, 'experience': 'EXPERIENCED'},
                'question': {'raw': {'text': question, 'wordCount': 10}},
                'answer': {
                    'raw': {'text': '원본 답변', 'wordCount': 30},
                    'summary': {'text': summary},
                },
            },
        }

    def test_ict_data_is_parsed_and_summary_is_preferred(self):
        result = parse_aihub_file(str(self.write_payload(self.payload())))
        self.assertEqual(result['job_category'], 'ICT')
        self.assertEqual(result['answer_example'], '요약 답변')
        self.assertEqual(result['question_type'], 'technical')

    def test_non_ict_and_missing_question_return_none(self):
        self.assertIsNone(parse_aihub_file(str(self.write_payload(self.payload('SALES')))))
        self.assertIsNone(parse_aihub_file(str(self.write_payload(self.payload(question='')))))

    def test_raw_answer_is_used_when_summary_is_missing(self):
        result = parse_aihub_file(str(self.write_payload(self.payload(summary=''))))
        self.assertEqual(result['answer_example'], '원본 답변')

    def test_unexpected_json_structure_returns_none(self):
        self.assertIsNone(parse_aihub_file(str(self.write_payload([]))))
