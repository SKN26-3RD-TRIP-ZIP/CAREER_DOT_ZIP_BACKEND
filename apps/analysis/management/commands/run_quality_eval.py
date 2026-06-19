"""
질문·답변 품질 평가 실행 (LLM-as-judge).

  python manage.py run_quality_eval

각 케이스를 채점하고 평균을 출력한다. expect_min_overall 미만이면 실패로 표시하고
하나라도 미달이면 exit code 1 (CI 게이트로 활용 가능).
OPENAI_API_KEY 필요.
"""

import sys

from django.core.management.base import BaseCommand

from apps.analysis.evals.judges import judge_question, judge_answer
from apps.analysis.evals.cases import QUESTION_CASES, ANSWER_CASES


class Command(BaseCommand):
    help = "면접 질문·답변 품질을 LLM-judge로 채점한다."

    def add_arguments(self, parser):
        parser.add_argument("--model", default="gpt-4o-mini", help="심판 모델")

    def handle(self, *args, **opts):
        model = opts["model"]
        failures = 0

        self.stdout.write(self.style.MIGRATE_HEADING("\n[질문 품질]"))
        for c in QUESTION_CASES:
            r = judge_question(c["question"], c["context"], model=model)
            failures += self._report(c["label"], r["overall"], c["expect_min_overall"], r)

        self.stdout.write(self.style.MIGRATE_HEADING("\n[답변 품질]"))
        for c in ANSWER_CASES:
            r = judge_answer(c["answer"], c["source"], model=model)
            extra = f" / 창작수치={r['hard_unsupported'] or '없음'}"
            failures += self._report(c["label"], r["overall"], c["expect_min_overall"], r, extra)

        if failures:
            self.stdout.write(self.style.ERROR(f"\n품질 미달 {failures}건 — 기준 미충족"))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS("\n모든 케이스 품질 기준 통과"))

    def _report(self, label, overall, threshold, detail, extra=""):
        passed = overall >= threshold
        mark = self.style.SUCCESS("PASS") if passed else self.style.ERROR("FAIL")
        self.stdout.write(
            f"  [{mark}] {label}: overall={overall} (기준 {threshold}){extra}"
        )
        if not passed:
            self.stdout.write(f"         사유: {detail.get('reason', '')}")
        return 0 if passed else 1
