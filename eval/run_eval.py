"""
LLM 성능 비교 평가 스크립트

대상 지표:
  11-2. 질문 생성 품질  — 직무 관련성, 질문 다양성, 구조 완성도
  11-2. JD 분석 품질   — 키워드 추출 완성도, 요건 추출 정확도
  11-4. 응답 성능       — Latency (P50/P95), 단계별 소요 시간, Error Rate

실행 방법:
  cd CAREER_DOT_ZIP_BACKEND
  pip install sentence-transformers numpy scipy
  python eval/run_eval.py
  python eval/run_eval.py --models gpt-4o-mini gpt-4o
  python eval/run_eval.py --models gpt-4o-mini gpt-4.1-mini --jd-only
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Django 설정 — CAREER_DOT_ZIP_BACKEND 루트에서 실행한다고 가정
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from apps.analysis.services.jd_service import extract_jd_keywords, extract_jd_requirements
from apps.analysis.services.resume_service import analyze_resume
from apps.analysis.services.question_gen_service import generate_questions
from apps.analysis.services.utils import get_client, get_embeddings, cosine_similarity

# ---------------------------------------------------------------------------
# 경로 상수
# ---------------------------------------------------------------------------
EVAL_DIR     = Path(__file__).resolve().parent
FIXTURES_DIR = EVAL_DIR / "fixtures"
OUTPUTS_DIR  = EVAL_DIR / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# 비교할 모델 기본값
# ---------------------------------------------------------------------------
DEFAULT_MODELS = ["gpt-4o-mini", "gpt-4o"]


# ===========================================================================
# 유틸
# ===========================================================================

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """OpenAI text-embedding-3-small으로 임베딩."""
    client = get_client()
    return get_embeddings(texts, client)


def pairwise_cosine_similarities(texts: list[str]) -> list[float]:
    """텍스트 목록 내 모든 쌍의 코사인 유사도를 반환."""
    if len(texts) < 2:
        return []
    embeddings = _embed_texts(texts)
    sims = []
    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            sims.append(cosine_similarity(embeddings[i], embeddings[j]))
    return sims


def percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = math.ceil(p / 100 * len(sorted_v)) - 1
    return sorted_v[max(idx, 0)]


# ===========================================================================
# 11-2-A  JD 분석 품질 평가
# ===========================================================================

def eval_jd_analysis(jd_samples: list[dict], model: str) -> dict:
    """
    지표:
      - tech_keyword_count    : 추출된 기술 키워드 수
      - trait_keyword_count   : 추출된 인재상 키워드 수
      - keyword_extraction_ok : tech + trait 모두 1개 이상 추출됐는지 (boolean)
      - requirements_ok       : required_tech 1개 이상, min_years 정수형 여부
      - latency_sec           : 각 샘플의 소요 시간
    """
    results = []
    latencies: list[float] = []
    errors = 0

    for sample in jd_samples:
        jd_id   = sample["id"]
        jd_text = sample["jd_text"]

        # ── extract_jd_keywords ──────────────────────────────────────────
        t0 = time.perf_counter()
        try:
            kw = extract_jd_keywords(jd_text, model=model)
            kw_latency = time.perf_counter() - t0
            kw_ok = True
        except Exception as e:
            kw = {}
            kw_latency = time.perf_counter() - t0
            kw_ok = False
            errors += 1
            print(f"  [ERROR] {jd_id} extract_jd_keywords: {e}")

        # ── extract_jd_requirements ──────────────────────────────────────
        t0 = time.perf_counter()
        try:
            req = extract_jd_requirements(jd_text, model=model)
            req_latency = time.perf_counter() - t0
            req_ok = True
        except Exception as e:
            req = {}
            req_latency = time.perf_counter() - t0
            req_ok = False
            errors += 1
            print(f"  [ERROR] {jd_id} extract_jd_requirements: {e}")

        total_latency = kw_latency + req_latency
        latencies.append(total_latency)

        tech_kws  = kw.get("tech_keywords", [])
        trait_kws = kw.get("trait_keywords", [])

        results.append({
            "jd_id":                jd_id,
            "model":                model,
            "tech_keyword_count":   len(tech_kws),
            "trait_keyword_count":  len(trait_kws),
            "keyword_extraction_ok": kw_ok and len(tech_kws) >= 1 and len(trait_kws) >= 1,
            "extracted_tech":       tech_kws,
            "extracted_trait":      trait_kws,
            "requirements_ok":      req_ok and len(req.get("required_tech", [])) >= 1 and isinstance(req.get("min_years"), int),
            "requirements":         req,
            "latency_kw_sec":       round(kw_latency, 3),
            "latency_req_sec":      round(req_latency, 3),
            "latency_total_sec":    round(total_latency, 3),
        })

    total_cases = len(jd_samples)
    extraction_success_rate = sum(1 for r in results if r["keyword_extraction_ok"]) / total_cases if total_cases else 0
    requirements_success_rate = sum(1 for r in results if r["requirements_ok"]) / total_cases if total_cases else 0

    return {
        "model":                      model,
        "total_cases":                total_cases,
        "error_count":                errors,
        "error_rate":                 round(errors / max(total_cases * 2, 1), 4),
        "keyword_extraction_success": round(extraction_success_rate, 4),
        "requirements_success":       round(requirements_success_rate, 4),
        "avg_tech_keyword_count":     round(sum(r["tech_keyword_count"] for r in results) / total_cases, 2) if total_cases else 0,
        "avg_trait_keyword_count":    round(sum(r["trait_keyword_count"] for r in results) / total_cases, 2) if total_cases else 0,
        "latency_p50_sec":            round(percentile(latencies, 50), 3),
        "latency_p95_sec":            round(percentile(latencies, 95), 3),
        "latency_avg_sec":            round(sum(latencies) / len(latencies), 3) if latencies else 0,
        "details":                    results,
    }


# ===========================================================================
# 11-2-B  질문 생성 품질 평가
# ===========================================================================

def eval_question_generation(
    resume_samples: list[dict],
    jd_samples: list[dict],
    model: str,
) -> dict:
    """
    지표:
      - question_count          : 생성된 질문 수 (목표: 10개)
      - type_distribution       : 인성/기술/경험 유형별 분포
      - structure_ok_rate       : text + source + basis 모두 있는 질문 비율
      - jd_relevance_score      : JD 원문 vs. 기술(technical) 질문만 코사인 유사도 평균
                                  (인성·경험 질문은 원래 기술 키워드와 무관하므로 제외)
      - diversity_index         : 질문 간 평균 유사도의 역수 (낮을수록 다양)
                                  목표: 질문 간 유사도 평균 ≤ 0.3
      - latency_sec             : 질문 생성 소요 시간
    """
    jd_map = {s["id"]: s for s in jd_samples}
    results = []
    latencies: list[float] = []
    errors = 0

    for sample in resume_samples:
        jd_id    = sample["jd_id"]
        jd_data  = jd_map.get(jd_id, {})
        jd_text  = jd_data.get("jd_text", "")
        job_role = jd_data.get("job_role", "")
        company  = jd_data.get("company_name", "")

        # JD 키워드 추출 (평가 전처리 — 모델 동일하게 사용)
        try:
            jd_keywords = extract_jd_keywords(jd_text, model=model)
        except Exception:
            jd_keywords = {"tech_keywords": [], "trait_keywords": []}

        # 이력서 분석 (평가 전처리)
        try:
            resume_analysis = analyze_resume(
                sample["resume_text"],
                sample["cover_letter_text"],
                model=model,
            )
        except Exception:
            resume_analysis = {"key_experiences": [], "projects": [], "trait_evidence": []}

        # ── generate_questions ───────────────────────────────────────────
        t0 = time.perf_counter()
        try:
            questions = generate_questions(
                job_role=job_role,
                company_name=company,
                jd_keywords=jd_keywords,
                resume_analysis=resume_analysis,
                model=model,
            )
            latency = time.perf_counter() - t0
            gen_ok = True
        except Exception as e:
            questions = []
            latency = time.perf_counter() - t0
            gen_ok = False
            errors += 1
            print(f"  [ERROR] {sample['id']} generate_questions: {e}")

        latencies.append(latency)

        # ── 지표 계산 ────────────────────────────────────────────────────
        q_texts = [q.get("text", "") for q in questions if q.get("text")]

        # 구조 완성도 (text + source + basis 모두 있는지)
        structure_ok = [
            bool(q.get("text") and q.get("source") and q.get("basis"))
            for q in questions
        ]
        structure_ok_rate = sum(structure_ok) / len(questions) if questions else 0

        # 유형별 분포
        type_dist = {"personality": 0, "technical": 0, "experience": 0}
        for q in questions:
            q_type = q.get("type", "")
            if q_type in type_dist:
                type_dist[q_type] += 1

        # 질문 다양성 — 질문 간 코사인 유사도 평균 (낮을수록 다양)
        diversity_sim_avg = 0.0
        if len(q_texts) >= 2:
            sims = pairwise_cosine_similarities(q_texts)
            diversity_sim_avg = sum(sims) / len(sims) if sims else 0.0

        # JD 관련성 — JD 원문 vs. 기술(technical) 질문만 코사인 유사도 측정
        # 인성·경험 질문은 원래 기술 키워드와 무관하므로 측정 대상에서 제외
        jd_relevance_avg = 0.0
        technical_q_texts = [
            q.get("text", "") for q in questions
            if q.get("type") == "technical" and q.get("text")
        ]
        if technical_q_texts and jd_text:
            all_texts = [jd_text] + technical_q_texts
            all_embs  = _embed_texts(all_texts)
            jd_emb    = all_embs[0]
            q_embs    = all_embs[1:]
            sims = [cosine_similarity(jd_emb, qe) for qe in q_embs]
            jd_relevance_avg = sum(sims) / len(sims) if sims else 0.0

        results.append({
            "resume_id":                sample["id"],
            "jd_id":                    jd_id,
            "model":                    model,
            "question_count":           len(questions),
            "type_distribution":        type_dist,
            "structure_ok_rate":        round(structure_ok_rate, 4),
            "jd_relevance_avg":         round(jd_relevance_avg, 4),
            "jd_relevance_basis":       f"technical 질문 {len(technical_q_texts)}개 vs JD 원문",
            "diversity_sim_avg":        round(diversity_sim_avg, 4),
            "diversity_ok":             diversity_sim_avg <= 0.3,
            "latency_sec":              round(latency, 3),
            "questions":                questions,
        })

    total_cases = len(resume_samples)

    return {
        "model":                    model,
        "total_cases":              total_cases,
        "error_count":              errors,
        "error_rate":               round(errors / max(total_cases, 1), 4),
        "avg_question_count":       round(sum(r["question_count"] for r in results) / total_cases, 2) if total_cases else 0,
        "avg_structure_ok_rate":    round(sum(r["structure_ok_rate"] for r in results) / total_cases, 4) if total_cases else 0,
        "avg_jd_relevance":         round(sum(r["jd_relevance_avg"] for r in results) / total_cases, 4) if total_cases else 0,
        "avg_diversity_sim":        round(sum(r["diversity_sim_avg"] for r in results) / total_cases, 4) if total_cases else 0,
        "diversity_goal_met_rate":  round(sum(1 for r in results if r["diversity_ok"]) / total_cases, 4) if total_cases else 0,
        "latency_p50_sec":          round(percentile(latencies, 50), 3),
        "latency_p95_sec":          round(percentile(latencies, 95), 3),
        "latency_avg_sec":          round(sum(latencies) / len(latencies), 3) if latencies else 0,
        "details":                  results,
    }


# ===========================================================================
# 비교 요약 테이블 출력
# ===========================================================================

def print_comparison(jd_evals: list[dict], q_evals: list[dict]) -> None:
    print("\n" + "=" * 70)
    print("  11-2  JD 분석 품질 비교")
    print("=" * 70)
    header = f"{'모델':<20} {'키워드추출성공':>14} {'요건추출성공':>12} {'평균기술KW':>10} {'P50(s)':>8} {'P95(s)':>8} {'ErrorRate':>10}"
    print(header)
    print("-" * 70)
    for r in jd_evals:
        print(
            f"{r['model']:<20}"
            f"{r['keyword_extraction_success']:>14.2%}"
            f"{r['requirements_success']:>12.2%}"
            f"{r['avg_tech_keyword_count']:>10.1f}"
            f"{r['latency_p50_sec']:>8.2f}"
            f"{r['latency_p95_sec']:>8.2f}"
            f"{r['error_rate']:>10.2%}"
        )

    print("\n" + "=" * 70)
    print("  11-2  질문 생성 품질 비교")
    print("=" * 70)
    header = f"{'모델':<20} {'평균질문수':>10} {'구조완성도':>10} {'JD관련성':>10} {'다양성유사도':>12} {'다양성목표':>10} {'P50(s)':>8} {'P95(s)':>8}"
    print(header)
    print("-" * 70)
    for r in q_evals:
        print(
            f"{r['model']:<20}"
            f"{r['avg_question_count']:>10.1f}"
            f"{r['avg_structure_ok_rate']:>10.2%}"
            f"{r['avg_jd_relevance']:>10.4f}"
            f"{r['avg_diversity_sim']:>12.4f}"
            f"{r['diversity_goal_met_rate']:>10.2%}"
            f"{r['latency_p50_sec']:>8.2f}"
            f"{r['latency_p95_sec']:>8.2f}"
        )

    print("\n" + "=" * 70)
    print("  11-4  응답 성능 종합")
    print("=" * 70)
    print(f"{'모델':<20} {'구간':<22} {'P50(s)':>8} {'P95(s)':>8} {'평균(s)':>8}")
    print("-" * 70)
    for jd_r, q_r in zip(jd_evals, q_evals):
        m = jd_r["model"]
        print(f"{m:<20} {'JD 분석 (kw+req)':<22} {jd_r['latency_p50_sec']:>8.2f} {jd_r['latency_p95_sec']:>8.2f} {jd_r['latency_avg_sec']:>8.2f}")
        print(f"{'':20} {'질문 생성':<22} {q_r['latency_p50_sec']:>8.2f} {q_r['latency_p95_sec']:>8.2f} {q_r['latency_avg_sec']:>8.2f}")
    print()


# ===========================================================================
# 메인
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="LLM 성능 비교 평가")
    parser.add_argument(
        "--models", nargs="+", default=DEFAULT_MODELS,
        help="비교할 모델 목록 (예: gpt-4o-mini gpt-4o gpt-4.1-mini)",
    )
    parser.add_argument("--jd-only", action="store_true", help="JD 분석만 평가")
    parser.add_argument("--q-only",  action="store_true", help="질문 생성만 평가")
    args = parser.parse_args()

    jd_samples     = load_json(FIXTURES_DIR / "jd_samples.json")
    resume_samples = load_json(FIXTURES_DIR / "resume_samples.json")

    run_jd = not args.q_only
    run_q  = not args.jd_only

    jd_eval_results: list[dict] = []
    q_eval_results:  list[dict] = []

    for model in args.models:
        print(f"\n{'─' * 50}")
        print(f"  모델: {model}")
        print(f"{'─' * 50}")

        if run_jd:
            print(f"  [JD 분석 평가] {len(jd_samples)}개 샘플...")
            jd_result = eval_jd_analysis(jd_samples, model=model)
            jd_eval_results.append(jd_result)
            print(f"  완료 — 키워드 추출 성공률: {jd_result['keyword_extraction_success']:.0%}, P95: {jd_result['latency_p95_sec']}s")

        if run_q:
            print(f"  [질문 생성 평가] {len(resume_samples)}개 샘플...")
            q_result = eval_question_generation(resume_samples, jd_samples, model=model)
            q_eval_results.append(q_result)
            print(f"  완료 — 평균 질문수: {q_result['avg_question_count']}, JD관련성: {q_result['avg_jd_relevance']:.4f}, P95: {q_result['latency_p95_sec']}s")

    # ── 비교 테이블 출력 ─────────────────────────────────────────────────
    if jd_eval_results and q_eval_results:
        print_comparison(jd_eval_results, q_eval_results)
    elif jd_eval_results:
        print_comparison(jd_eval_results, [{"model": r["model"], "avg_question_count": 0, "avg_structure_ok_rate": 0, "avg_jd_relevance": 0, "avg_diversity_sim": 0, "diversity_goal_met_rate": 0, "latency_p50_sec": 0, "latency_p95_sec": 0, "latency_avg_sec": 0} for r in jd_eval_results])

    # ── 결과 저장 ────────────────────────────────────────────────────────
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUTS_DIR / f"eval_report_{timestamp}.json"

    output_payload = {
        "created_at":    datetime.now().isoformat(timespec="seconds"),
        "models":        args.models,
        "jd_evaluation": jd_eval_results,
        "q_evaluation":  q_eval_results,
    }
    output_path.write_text(
        json.dumps(output_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"결과 저장: {output_path}\n")


if __name__ == "__main__":
    main()
