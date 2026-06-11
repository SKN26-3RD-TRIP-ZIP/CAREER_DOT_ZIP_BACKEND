# -*- coding: utf-8 -*-
"""
Career.zip 답변평가 엔진 — LLM 모델 성능 비교 벤치마크 하니스
=============================================================
담당: 박은지 (evaluation / report)

목적
----
답변평가(Track 1)의 핵심 LLM 호출 두 가지
  - fetch_competency : BEI(STAR) + CBI 역량 채점
  - fetch_grounding  : 기술 근거(tech_stack / before / after) + is_grounded
를 여러 OpenAI 모델로 각각 수행하고, 전문 면접관 Ground-Truth(benchmark_dataset.jsonl)
대비 정확도를 프로젝트 기획서 11-3 지표(MAE / Pearson r / Cohen's Kappa / Cosine)로
산출한다.

실행
----
  # 1) 실제 OpenAI 호출 (로컬, API 키 필요)
  export OPENAI_API_KEY=sk-...
  python llm_eval_benchmark.py --models gpt-4o-mini gpt-4.1-mini gpt-4.1

  # 2) 호출 비용 절감: 핵심 기능(competency)만 평가
  python llm_eval_benchmark.py --skip-grounding

  # 3) API 없이 지표 계산 로직만 검증 (mock 엔진)
  python llm_eval_benchmark.py --engine mock

출력
----
  results_summary.csv      모델 × 지표 요약
  results_per_answer.csv   답변 × 모델 상세 예측
  results_summary.md       마크다운 결과표 (보고서 붙여넣기용)

의존성: openai (실호출 시에만). 지표는 순수 파이썬 구현 — 추가 패키지 불필요.
"""
import argparse, json, math, os, statistics, sys, time, hashlib, csv

# ----------------------------------------------------------------------------
# 평가 프롬프트 (apps/evaluation/evaluation_prompts.py 와 동일 — 단독 실행 위해 인라인)
# ----------------------------------------------------------------------------
EVAL_COMPETENCY_SYSTEM_PROMPT = """당신은 대기업 최고 실무진 및 직무 역량 평가 위원입니다.
제공된 지원자의 면접 답변(STT 텍스트)을 바탕으로 [BEI 구조화] 및 [CBI 역량 루브릭 채점]을 엄격하게 수행하십시오.

[RULE 1] BEI STAR 구조화 및 채점 (요소별 25점, 총 100점)
1. situation(25): 문제 상황·배경이 명확한가? (부실 시 10점 이하)
2. task(25): 목표와 한계점이 구체적인가?
3. action(25): 지원자 '본인'이 취한 구체적 기술 노력인가? (주어 '우리' 지양, 부실 시 10점 이하)
4. result(25): 성과가 명확한가? (추상적 회고 시 12점 이하)

[RULE 2] CBI '문제해결역량' 레벨
- Level 1: 지시받은 업무만 단순 수행
- Level 2: 문제 인지 후 관습적 해결 시도
- Level 3: 대안 비교·논리적 근거(인덱스/쿼리튜닝 등) 기반 주도적 해결
- Level 4: 재발 방지 자동화·모니터링 체계 구축·팀 가이드라인 전파까지 완료
"""

EVAL_COMPETENCY_FORMAT_PROMPT = """
반드시 아래 JSON 스키마를 100% 준수하고 부가 설명은 절대 포함하지 마십시오.
{
  "bei_star": {
    "situation": {"desc": "요약", "score": 20},
    "task": {"desc": "요약", "score": 20},
    "action": {"desc": "요약", "score": 25},
    "result": {"desc": "요약", "score": 20}
  },
  "cbi_competency": {"assigned_level": 3, "score": 60, "evidence_sentence": "근거 문장"}
}
"""

EVAL_GROUNDING_SYSTEM_PROMPT = """당신은 기술 면접 답변의 실무 객관성을 검증하는 정량 지표 분석 엔진입니다.
아래 3대 지표를 추출하고 순수 JSON 하나만 반환하십시오.
1. tech_stack: 라이브러리/프레임워크/DB/아키텍처 명칭
2. before_metric: 개선 전 정량 수치(ms,%,원 등 단위 포함)
3. after_metric: 개선 후 정량 수치(단위 포함)
[CORE RULE] 3대 지표가 모두 유의미하게 존재할 때만 is_grounded=true, 하나라도 결손/추상/"없음"이면 false.
is_grounded 는 따옴표 없는 순수 Boolean(true/false). 마크다운 래퍼·설명 없이 아래 포맷만:
{"tech_stack":"FastAPI, Redis","before_metric":"조회 500ms","after_metric":"50ms로 90% 단축","is_grounded":true}"""

# ----------------------------------------------------------------------------
# 점수 환산 (docs/evaluation_score_guide.md 7절과 동일)
# speech_score 는 모델 비종속(로컬 kiwipiepy 분석)이므로 모든 모델에 GT 값을 고정 적용 →
# 순수 LLM 품질(BEI/CBI/grounding)만 분리 비교.
# ----------------------------------------------------------------------------
def compute_overall(bei_total, cbi_score, speech_score, is_grounded, qtype):
    if qtype == "technical":
        prem = 15 if is_grounded else 0
        raw = bei_total * 0.4 + cbi_score * 0.4 + speech_score * 0.2 + prem
    else:
        raw = bei_total * 0.5 + cbi_score * 0.3 + speech_score * 0.2
    return round(min(raw, 100.0), 1)

# ----------------------------------------------------------------------------
# 지표 (순수 파이썬; scipy.stats.pearsonr / sklearn 과 수치 일치)
# ----------------------------------------------------------------------------
def mae(y_true, y_pred):
    return sum(abs(a - b) for a, b in zip(y_true, y_pred)) / len(y_true)

def rmse(y_true, y_pred):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(y_true, y_pred)) / len(y_true))

def pearson_r(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx == 0 or sy == 0:
        return float("nan")
    return cov / (sx * sy)

def cohens_kappa(y_true, y_pred):
    """범주형(불리언/정수 레벨) 평가자 간 일치도. 우연 일치 보정."""
    labels = sorted(set(y_true) | set(y_pred))
    idx = {l: i for i, l in enumerate(labels)}
    k = len(labels)
    n = len(y_true)
    m = [[0] * k for _ in range(k)]
    for t, p in zip(y_true, y_pred):
        m[idx[t]][idx[p]] += 1
    po = sum(m[i][i] for i in range(k)) / n
    row = [sum(m[i]) for i in range(k)]
    col = [sum(m[i][j] for i in range(k)) for j in range(k)]
    pe = sum((row[i] / n) * (col[i] / n) for i in range(k))
    if pe == 1:
        return 1.0
    return (po - pe) / (1 - pe)

def cosine_sim(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return float("nan")
    return dot / (na * nb)

# ----------------------------------------------------------------------------
# 엔진: 실제 OpenAI 호출 / mock(오프라인 검증용)
# ----------------------------------------------------------------------------
def _load_api_key():
    """OPENAI_API_KEY 를 환경변수에서, 없으면 현재~상위 폴더를 거슬러 올라가며 .env 에서 로드.
    (폴더 위치/깊이가 바뀌어도 동작하도록 부모 디렉터리를 최대 6단계까지 탐색)"""
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    here = os.path.abspath(os.path.dirname(__file__))
    for _ in range(6):
        env_path = os.path.join(here, ".env")
        if os.path.exists(env_path):
            for line in open(env_path, encoding="utf-8"):
                line = line.strip()
                if line.startswith("OPENAI_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    raise RuntimeError(
        "OPENAI_API_KEY 를 찾지 못했습니다. 환경변수로 export 하거나 "
        "백엔드 .env 에 OPENAI_API_KEY=... 가 있는지 확인하세요."
    )


class OpenAIEngine:
    def __init__(self, model, temperature=0.0):
        from openai import OpenAI
        self.model = model
        self.temperature = temperature
        self.client = OpenAI(api_key=_load_api_key())

    def _call(self, system, user):
        t0 = time.time()
        kwargs = dict(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            timeout=30.0,
        )
        # 일부 신모델은 temperature 커스텀을 막아(기본 1만 허용) 400을 낼 수 있음 → 그 경우 생략
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        try:
            res = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            if "temperature" in str(e).lower():
                kwargs.pop("temperature", None)
                res = self.client.chat.completions.create(**kwargs)
            else:
                raise
        dt = time.time() - t0
        usage = res.usage
        return (json.loads(res.choices[0].message.content), dt,
                usage.prompt_tokens, usage.completion_tokens)

    def competency(self, text):
        sys_p = f"{EVAL_COMPETENCY_SYSTEM_PROMPT}\n\n{EVAL_COMPETENCY_FORMAT_PROMPT}"
        return self._call(sys_p, text)

    def grounding(self, text):
        return self._call(EVAL_GROUNDING_SYSTEM_PROMPT, text)


class MockEngine:
    """API 없이 지표 파이프라인을 검증. GT에 모델별 결정적 노이즈를 주입해
    '완벽하지 않은 모델'을 시뮬레이션한다. 정확도 평가용 아님 — 코드 검증 전용."""
    def __init__(self, model, gt_index, noise):
        self.model = model
        self.gt = gt_index           # id -> ground_truth dict
        self.noise = noise           # 모델별 노이즈 강도

    def _seed(self, text):
        h = hashlib.md5((self.model + text).encode()).hexdigest()
        return int(h[:8], 16) / 0xFFFFFFFF  # 0~1

    def competency(self, text):
        gt = self._lookup(text)
        s = self._seed(text)
        delta = round((s - 0.5) * 2 * self.noise)  # -noise..+noise
        bei = gt["bei"]
        jit = lambda v: max(0, min(25, v + delta))
        lvl = max(1, min(5, gt["cbi_level"] + (1 if s > 0.8 else (-1 if s < 0.2 else 0))))
        out = {"bei_star": {
                   "situation": {"desc": "", "score": jit(bei["situation"])},
                   "task": {"desc": "", "score": jit(bei["task"])},
                   "action": {"desc": "", "score": jit(bei["action"])},
                   "result": {"desc": "", "score": jit(bei["result"])}},
               "cbi_competency": {"assigned_level": lvl, "score": lvl * 20, "evidence_sentence": ""}}
        return out, 0.2 + s * 0.3, 800, 180

    def grounding(self, text):
        gt = self._lookup(text); s = self._seed(text + "g")
        flip = s < (self.noise / 30.0)  # 노이즈에 비례해 가끔 오판
        g = gt["is_grounded"] ^ flip
        out = {"tech_stack": "x", "before_metric": "x", "after_metric": "x", "is_grounded": bool(g)}
        return out, 0.1 + s * 0.2, 400, 60

    def _lookup(self, text):
        for rec in self.gt.values():
            if rec["answer_text"] == text:
                return rec["ground_truth"]
        raise KeyError("mock: 답변 텍스트를 GT에서 못 찾음")

# ----------------------------------------------------------------------------
# 대략적 가격표 (USD / 1M tokens, 2026-06 기준; 변동 가능)
# ----------------------------------------------------------------------------
PRICING = {
    "gpt-4o-mini":  (0.15, 0.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1":      (2.00, 8.00),
    "gpt-4o":       (2.50, 10.00),
    "gpt-5.5":      (5.00, 30.00),
}

def parse_competency(obj):
    bei = obj["bei_star"]
    g = lambda k: float(bei[k]["score"])
    s, t, a, r = g("situation"), g("task"), g("action"), g("result")
    lvl = int(obj["cbi_competency"]["assigned_level"])
    return [s, t, a, r], s + t + a + r, lvl, lvl * 20

# ----------------------------------------------------------------------------
def run_model(model, engine, data, skip_grounding):
    rows, fails = [], 0
    pin = pout = 0
    for rec in data:
        gt = rec["ground_truth"]
        text = rec["answer_text"]; qtype = rec["interview_type"]
        try:
            comp, dt1, p1, o1 = engine.competency(text)
            bei_vec, bei_total, cbi_lvl, cbi_score = parse_competency(comp)
            if skip_grounding:
                grounded = gt["is_grounded"]; dt2 = p2 = o2 = 0
            else:
                gr, dt2, p2, o2 = engine.grounding(text)
                grounded = bool(gr["is_grounded"])
            pin += p1 + p2; pout += o1 + o2
            pred_overall = compute_overall(bei_total, cbi_score,
                                           gt["speech_score"], grounded, qtype)
            rows.append({
                "id": rec["id"], "qtype": qtype,
                "gt_overall": gt["overall_score"], "pred_overall": pred_overall,
                "gt_bei_vec": gt["bei"], "pred_bei_vec": bei_vec, "pred_bei_total": bei_total,
                "gt_cbi": gt["cbi_level"], "pred_cbi": cbi_lvl,
                "gt_grounded": int(gt["is_grounded"]), "pred_grounded": int(grounded),
                "latency_s": round(dt1 + dt2, 3),
            })
        except Exception as e:
            fails += 1
            print(f"  [WARN] {model} / {rec['id']} 실패: {type(e).__name__}: {e}", file=sys.stderr)
    return rows, fails, pin, pout

def summarize(model, rows, fails, pin, pout, n_total):
    gt_o  = [r["gt_overall"] for r in rows]
    pr_o  = [r["pred_overall"] for r in rows]
    gt_g  = [r["gt_grounded"] for r in rows]
    pr_g  = [r["pred_grounded"] for r in rows]
    gt_c  = [r["gt_cbi"] for r in rows]
    pr_c  = [r["pred_cbi"] for r in rows]
    # Cosine: 답변별 5차원 점수 프로파일[s,t,a,r,cbi_score]의 코사인 유사도 평균
    cos_list = []
    for r in rows:
        gv = [r["gt_bei_vec"]["situation"], r["gt_bei_vec"]["task"],
              r["gt_bei_vec"]["action"], r["gt_bei_vec"]["result"], r["gt_cbi"] * 20]
        pv = r["pred_bei_vec"] + [r["pred_cbi"] * 20]
        cos_list.append(cosine_sim(gv, pv))
    ip, op = PRICING.get(model, (None, None))
    cost = None
    if ip is not None and rows:
        cost = (pin / 1e6 * ip + pout / 1e6 * op) / len(rows)
    return {
        "model": model,
        "n": len(rows),
        "MAE": round(mae(gt_o, pr_o), 2) if rows else None,
        "RMSE": round(rmse(gt_o, pr_o), 2) if rows else None,
        "Pearson_r": round(pearson_r(gt_o, pr_o), 3) if rows else None,
        "Kappa_grounded": round(cohens_kappa(gt_g, pr_g), 3) if rows else None,
        "Kappa_cbi": round(cohens_kappa(gt_c, pr_c), 3) if rows else None,
        "Cosine": round(statistics.mean(cos_list), 3) if cos_list else None,
        "JSON_fail_rate": round(fails / n_total, 3),
        "avg_latency_s": round(statistics.mean([r["latency_s"] for r in rows]), 3) if rows else None,
        "est_cost_usd_per_answer": round(cost, 6) if cost is not None else None,
    }

TARGETS = {"MAE": "≤ 5.0", "Pearson_r": "≥ 0.75", "Kappa_grounded": "≥ 0.60",
           "Kappa_cbi": "≥ 0.60", "Cosine": "≥ 0.70"}

AGG_METRICS = ["MAE", "RMSE", "Pearson_r", "Kappa_grounded", "Kappa_cbi", "Cosine"]

def aggregate_runs(model, run_summaries):
    """여러 run 요약을 평균±표준편차로 집계 (runs>1일 때 변동성 표시)."""
    agg = {"model": model, "n": run_summaries[0]["n"], "runs": len(run_summaries)}
    for m in AGG_METRICS:
        vals = [s[m] for s in run_summaries if s[m] is not None]
        if not vals:
            agg[m] = None; continue
        mean = statistics.mean(vals)
        std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        agg[m] = round(mean, 3)
        agg[m + "_std"] = round(std, 3)
    # 비용/지연/실패율은 평균
    for m in ("JSON_fail_rate", "avg_latency_s", "est_cost_usd_per_answer"):
        vals = [s[m] for s in run_summaries if s[m] is not None]
        agg[m] = round(statistics.mean(vals), 6) if vals else None
    return agg

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+",
                    default=["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1"])
    ap.add_argument("--dataset", default="benchmark_dataset.jsonl")
    ap.add_argument("--engine", choices=["openai", "mock"], default="openai")
    ap.add_argument("--skip-grounding", action="store_true",
                    help="핵심 기능(competency)만 평가해 호출 횟수 절반으로 축소")
    ap.add_argument("--temperature", type=float, default=0.0,
                    help="샘플링 온도(기본 0.0=결정적). run 간 변동성 최소화")
    ap.add_argument("--runs", type=int, default=1,
                    help="모델별 반복 측정 횟수. >1이면 평균±표준편차로 변동성 보고")
    args = ap.parse_args()

    data = [json.loads(l) for l in open(args.dataset, encoding="utf-8") if l.strip()]
    gt_index = {r["id"]: r for r in data}
    n_total = len(data)
    print(f"데이터셋 {n_total}개 답변 / 모델 {args.models} / engine={args.engine}"
          f" / skip_grounding={args.skip_grounding} / temp={args.temperature} / runs={args.runs}\n")

    summaries, per_answer = [], []
    mock_noise = {"gpt-4o-mini": 6, "gpt-4.1-mini": 3, "gpt-4.1": 1.5}
    for model in args.models:
        run_summaries = []
        for run_i in range(args.runs):
            tag = f" (run {run_i+1}/{args.runs})" if args.runs > 1 else ""
            print(f"▶ {model} 평가 중...{tag}")
            if args.engine == "mock":
                eng = MockEngine(model, gt_index, mock_noise.get(model, 4))
            else:
                eng = OpenAIEngine(model, temperature=args.temperature)
            rows, fails, pin, pout = run_model(model, eng, data, args.skip_grounding)
            run_summaries.append(summarize(model, rows, fails, pin, pout, n_total))
            if run_i == 0:
                for r in rows:
                    per_answer.append({"model": model, **{k: r[k] for k in
                        ("id", "qtype", "gt_overall", "pred_overall",
                         "gt_cbi", "pred_cbi", "gt_grounded", "pred_grounded", "latency_s")}})
        summaries.append(aggregate_runs(model, run_summaries) if args.runs > 1
                         else run_summaries[0])

    multi = args.runs > 1
    cols = ["model", "n"] + (["runs"] if multi else []) + \
           ["MAE", "RMSE", "Pearson_r", "Kappa_grounded", "Kappa_cbi", "Cosine"] + \
           ([m + "_std" for m in AGG_METRICS] if multi else []) + \
           ["JSON_fail_rate", "avg_latency_s", "est_cost_usd_per_answer"]
    with open("results_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(summaries)
    with open("results_per_answer.csv", "w", newline="", encoding="utf-8") as f:
        pcols = ["model", "id", "qtype", "gt_overall", "pred_overall",
                 "gt_cbi", "pred_cbi", "gt_grounded", "pred_grounded", "latency_s"]
        w = csv.DictWriter(f, fieldnames=pcols); w.writeheader(); w.writerows(per_answer)

    # 마크다운 표 (runs>1이면 mean±std)
    def cell(s, m):
        v = s.get(m)
        if v is None:
            return "—"
        if multi and (m + "_std") in s:
            return f"{v}±{s[m + '_std']}"
        return f"{v}"
    md = ["| 모델 | n | MAE | RMSE | Pearson r | Kappa(grounded) | Kappa(CBI) | Cosine | JSON실패율 | 지연(s) | $/답변 |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in summaries:
        md.append("| {model} | {n} | {MAE} | {RMSE} | {Pr} | {Kg} | {Kc} | {Cos} | "
                  "{fail} | {lat} | {cost} |".format(
                      model=s["model"], n=s["n"],
                      MAE=cell(s, "MAE"), RMSE=cell(s, "RMSE"), Pr=cell(s, "Pearson_r"),
                      Kg=cell(s, "Kappa_grounded"), Kc=cell(s, "Kappa_cbi"), Cos=cell(s, "Cosine"),
                      fail=s["JSON_fail_rate"], lat=s["avg_latency_s"],
                      cost=s["est_cost_usd_per_answer"]))
    md.append("")
    md.append("**목표 기준(11-3):** MAE " + TARGETS["MAE"] + " · Pearson r " + TARGETS["Pearson_r"]
              + " · Cohen's Kappa " + TARGETS["Kappa_grounded"] + " · Cosine " + TARGETS["Cosine"])
    open("results_summary.md", "w", encoding="utf-8").write("\n".join(md))

    print("\n" + "\n".join(md))
    print("\n저장: results_summary.csv / results_per_answer.csv / results_summary.md")

if __name__ == "__main__":
    main()
