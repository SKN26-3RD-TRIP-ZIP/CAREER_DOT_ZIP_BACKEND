# LLM 모델 성능 비교 평가서 — 답변평가 엔진 (Track 1)

**프로젝트:** Career.zip (SK네트웍스 Family AI 캠프 26기)
**담당 모듈:** Evaluation / Report — 박은지
**작성일:** 2026-06-11
**기준 문서:** 프로젝트 기획서 11-3. 답변 평가 정확도 지표 · `docs/evaluation_score_guide.md`

---

## 1. 평가 목적

답변평가 엔진은 사용자의 면접 답변(STT 텍스트)을 LLM으로 채점한다. 이 채점 점수가 **전문 면접관의 평가(Ground Truth)와 얼마나 일치하는가**가 서비스 신뢰도의 핵심이다. 본 평가서는 채점에 사용할 LLM 모델을 후보군에서 비교해, 기획서 11-3의 목표 지표를 충족하면서 비용 대비 효율이 가장 좋은 모델을 선정하는 것을 목적으로 한다.

현재 운영 코드(`apps/evaluation/evaluation_chains.py`)는 채점에 `gpt-4o-mini`를 사용하고 있다. 본 평가는 이 현행 모델을 기준선(baseline)으로 두고 상위 모델과 비교한다.

---

## 2. 평가 범위 — 핵심 기능 선정

답변 1건을 채점할 때 LLM은 **2회 호출**된다.

| 호출 | 함수 | 산출물 | 점수 기여 |
|---|---|---|---|
| ① 역량 채점 | `fetch_competency` | BEI(STAR 4요소) + CBI 역량 레벨 | **기술면접 80% / 인성면접 80%** (BEI 0.4~0.5 + CBI 0.3~0.4) |
| ② 근거 검증 | `fetch_grounding` | tech_stack / before / after / `is_grounded` | 기술면접 grounding premium +15점(조건부) |

답변 수 × 2회 호출이라 LLM 호출 비용이 빠르게 누적된다. 따라서 **최종 점수의 80%를 좌우하는 ①역량 채점(`fetch_competency`)을 핵심 기능으로 우선 평가**하고, ②근거 검증은 보조 지표(`is_grounded` 일치도)로 함께 측정한다. 하니스의 `--skip-grounding` 옵션으로 호출 횟수를 절반(21회)으로 줄여 핵심 기능만 평가할 수 있다.

---

## 3. 비교 대상 모델

코드베이스가 OpenAI 기반이므로 OpenAI 라인업 내에서 비교한다. 가격은 2026-06 기준 USD / 1M tokens (변동 가능).

| 모델 | 포지션 | Input | Output | 비고 |
|---|---|---|---|---|
| **gpt-4o-mini** | 현행 baseline | $0.15 | $0.60 | 운영 중 |
| gpt-4.1-nano | 초저비용 대안 | $0.10 | $0.40 | 최저가 |
| **gpt-4.1-mini** | 균형(권장 검토) | $0.40 | $1.60 | structured output 강점 |
| gpt-4.1 | 고정확도 | $2.00 | $8.00 | 1M 컨텍스트 |
| gpt-5.5 | 정확도 상한(참고) | $5.00 | $30.00 | 현행 플래그십 |

호출 비용을 고려해 1차 비교는 **gpt-4o-mini · gpt-4.1-mini · gpt-4.1** 3종으로 진행하고, 필요 시 nano(하한)·5.5(상한)를 추가한다.

---

## 4. 평가 방법론

### 4-1. 11-3 지표 매핑

기획서 11-3의 네 지표를 LLM 채점 점수 비교에 적용했다. (Cosine는 본래 Track 1 SBERT 임베딩용 지표이나, 모델 채점 결과 비교에는 **점수 프로파일 벡터의 코사인 유사도**로 적응 적용했다.)

| 지표 | 본 평가에서의 측정 대상 | 목표 기준 |
|---|---|---|
| **MAE** | 모델 종합점수 vs 전문가 종합점수(0~100) 절대오차 평균 | 평균 **5점 이내** |
| **Pearson r** | 모델·전문가 종합점수의 선형 상관 | **r ≥ 0.75** |
| **Cohen's Kappa** | `is_grounded`(불리언) 및 CBI 레벨(1~5) 판정 일치도(우연 보정) | **K ≥ 0.60** |
| **Cosine** | 답변별 점수 프로파일 `[situation, task, action, result, CBI]` 코사인 유사도 평균 | **평균 0.70 이상** |

보조 지표로 **RMSE**(큰 오차 민감), **JSON 파싱 실패율**(출력 안정성), **평균 지연(s)**, **답변당 추정 비용($)**을 함께 수집한다.

### 4-2. 점수 환산 (모델 비종속 변수 통제)

`speech_score`(발화 유창성)는 로컬 형태소 분석(kiwipiepy) 결과로 **모델과 무관**하다. 따라서 모든 모델에 동일한 Ground-Truth `speech_score`를 고정 적용해, 순수하게 **LLM이 담당하는 BEI·CBI·grounding 품질만** 분리 비교한다. 종합점수 산출식은 `evaluation_score_guide.md` 7절과 동일하다.

```
technical : raw = bei_total*0.4 + cbi_score*0.4 + speech_score*0.2 + (grounded ? 15 : 0)
그 외     : raw = bei_total*0.5 + cbi_score*0.3 + speech_score*0.2
final = min(raw, 100)
```

### 4-3. 벤치마크 데이터셋 (Ground Truth)

프로토타입 샘플 세션(`sess_001~003`)의 실제 면접 답변 **21건**에 대해, 담당자가 `evaluation_score_guide.md` 루브릭을 적용해 전문 면접관 기준 점수를 직접 라벨링했다(`benchmark_dataset.jsonl`). 품질 구간이 명확히 분포해 상관·오차 측정에 적합하다.

| 세션 | 직무 | 답변 수 | 품질 특성 | 종합점수 분포 |
|---|---|---|---|---|
| sess_01 | senior_backend | 7 | 우수 (정량 성과·STAR 충실) | 68 ~ 100 |
| sess_02 | data_analyst | 7 | 혼재 (일부 근거 부족) | 56 ~ 75 |
| sess_03 | ml_data_engineer | 7 | 미흡 (필러 과다·JD 불일치·수동적) | 35 ~ 44 |

전체 21건: 평균 64.0 · 표준편차 20.4 · `is_grounded` True 3건 / False 18건.

---

## 5. 정성 비교 분석

실측 호출(4·6절) 이전에, 각 모델의 공개된 특성과 본 과제(한국어·구조화 JSON·루브릭 채점) 적합도를 기준으로 예상 우열을 정리한다. **아래는 모델 특성 기반 정성 추정이며, 확정 수치는 6절 하니스 실행으로 대체한다.**

| 항목 | gpt-4o-mini (현행) | gpt-4.1-mini (권장 검토) | gpt-4.1 |
|---|---|---|---|
| 한국어 채점 일관성 | 보통 — 경계 답변(중간 품질)에서 점수 흔들림 | 양호 | 우수 |
| 루브릭 준수(STAR 4요소 분리) | 가끔 요소 혼동 | 안정적 | 매우 안정적 |
| JSON 스키마 준수 | 대체로 양호, 드물게 키 누락 | 강함(structured output) | 강함 |
| `is_grounded` 판정 엄격성 | 관대 편향(과채점) 경향 | 기준 근접 | 기준 근접~보수 |
| 비용 | ◎ 최저 | ○ 중간(현행의 약 2.7배) | △ 높음(현행의 약 13배) |
| 지연 | ◎ 빠름 | ○ | △ |

**예상 결론(사전):** 정확도는 `gpt-4.1 ≥ gpt-4.1-mini > gpt-4o-mini`, 비용효율은 역순으로 추정했다.

> ⚠️ **실측 결과 일부 반전:** 6장 측정에서 gpt-4.1-mini가 gpt-4.1보다 우수했다(루브릭 채점은 추론력보다 지시 준수·일관성이 핵심이라 모델 크기와 정확도가 비례하지 않음). 자세한 내용은 6-3·7장 참조.

---

## 6. 정량 평가 결과

> **실측 완료(2026-06-12):** 로컬 환경에서 `llm_eval_benchmark.py`로 4종 모델 × 21답변 × 2호출(competency+grounding)을 실제 OpenAI 호출로 측정했다. 아래는 실측치다.

### 6-1. 실측 결과 표 (4종)

| 모델 | n | MAE | RMSE | Pearson r | Kappa(grounded) | Kappa(CBI) | Cosine | JSON실패율 | 지연(s) | $/답변 |
|---|---|---|---|---|---|---|---|---|---|---|
| gpt-4o-mini (현행) | 21 | 9.36 | 11.51 | 0.841 | 0.323 | 0.420 | 0.989 | 0.0 | 4.315 | 0.000249 |
| gpt-4o | 21 | 8.75 | 11.21 | 0.841 | 0.462 | 0.413 | 0.984 | 0.0 | 4.525 | 0.004094 |
| **gpt-4.1-mini** | 21 | **5.90** | **8.19** | **0.926** | **0.774** | 0.468 | **0.990** | 0.0 | 5.212 | 0.000687 |
| gpt-4.1 | 21 | 8.37 | 11.05 | 0.885 | 0.146 | 0.468 | 0.987 | 0.0 | 3.520 | 0.003459 |

### 6-2. 목표 기준 대비 판정 (11-3)

| 지표 | 목표 | gpt-4o-mini | gpt-4o | gpt-4.1-mini | gpt-4.1 |
|---|---|---|---|---|---|
| MAE | ≤ 5.0 | 9.36 ✗ | 8.75 ✗ | 5.90 △(근접) | 8.37 ✗ |
| Pearson r | ≥ 0.75 | 0.841 ✓ | 0.841 ✓ | 0.926 ✓ | 0.885 ✓ |
| Kappa(grounded) | ≥ 0.60 | 0.323 ✗ | 0.462 ✗ | **0.774 ✓** | 0.146 ✗ |
| Kappa(CBI) | ≥ 0.60 | 0.420 ✗ | 0.413 ✗ | 0.468 ✗ | 0.468 ✗ |
| Cosine | ≥ 0.70 | 0.989 ✓ | 0.984 ✓ | 0.990 ✓ | 0.987 ✓ |

### 6-3. 결과 해석

- **gpt-4.1-mini가 모든 정확도 지표에서 1위.** MAE(5.90)·Pearson(0.926)·Kappa(grounded)(0.774)·Cosine(0.990) 전부 최고이며, 5개 목표 중 4개 통과(MAE만 경계값). 4종 중 유일하게 Kappa(grounded) 목표를 넘겼다.
- **gpt-4o는 도입 이유가 없다.** 정확도는 4.1-mini보다 전 항목 열세인데(MAE 8.75 vs 5.90, Pearson 동일) 비용은 답변당 $0.0041로 **4.1-mini의 약 6배**다. 비용·정확도 둘 다 4.1-mini에 밀린다.
- **"클수록 좋다"가 성립하지 않음.** 최상위 gpt-4.1이 4.1-mini보다 MAE·Kappa 모두 열세(MAE 8.37, Kappa-grounded 0.146)다. 루브릭 채점은 추론력보다 *지시 준수·일관성*이 핵심이라 모델 크기와 정확도가 비례하지 않는다. → 비용 5배인 gpt-4.1 제외.
- **공통 약점은 `is_grounded` 판정(+ run 간 변동성 큼).** grounded=True가 3/21로 적어 Kappa가 클래스 불균형에 매우 민감하다. 실제로 동일 설정 2회 실측에서 4.1-mini의 Kappa(grounded)가 0.462→0.774, 4.1이 0.391→0.146으로 크게 출렁였다(temperature 미고정에 따른 샘플링 변동 + 소표본 효과). is_grounded는 +15점 premium을 좌우해 MAE 변동의 주원인이기도 하다. → 7-2의 *온도 고정·반복 측정*과 *평가셋 재균형*이 필수.
- **JSON 실패율 0%·지연 유사.** 출력 안정성은 네 모델 모두 문제없고(파싱 실패 0건), 지연도 3.5~5.2초로 유사해 모델 선택의 변수는 아니다.

### 6-4. 사전 파이프라인 검증 (mock, 참고)

실측 전 지표 계산 로직 검증용으로 `--engine mock`(GT에 모델별 노이즈 주입)을 돌려, 모델 품질↑ 시 MAE↓·Pearson↑·Kappa↑로 단조 변화함을 확인했다(아래는 코드 검증용 시뮬레이션, 실제 정확도 아님). 순수 파이썬 지표 구현은 `scipy.stats.pearsonr`·`sklearn.metrics.cohen_kappa_score`·`cosine_similarity`와 소수점 6자리까지 일치 검증했다.

| 모델(mock) | MAE | Pearson r | Kappa(grounded) | Cosine |
|---|---|---|---|---|
| gpt-4o-mini | 10.23 | 0.811 | 0.500 | 0.994 |
| gpt-4.1-mini | 4.81 | 0.952 | 0.696 | 0.993 |
| gpt-4.1 | 2.50 | 0.979 | 1.000 | 0.996 |

## 7. 권장안 (실측 기반)

### 7-1. 모델 선정: `gpt-4o-mini` → **`gpt-4.1-mini` 로 승급 권장**

현행 gpt-4o-mini는 MAE 9.36·Kappa(grounded) 0.32로 목표를 크게 미달한다. **gpt-4.1-mini는 4종 중 모든 정확도 지표 1위**이며 5개 목표 중 4개 통과(MAE만 경계값 5.90), 추가 비용(답변당 +$0.0004)이 미미한 데 비해 정확도 개선폭이 크다. gpt-4o(정확도 열세·비용 6배)와 gpt-4.1(4.1-mini보다 열세·비용 5배)은 모두 **선택지에서 제외**한다.

### 7-2. 잔여 과제: MAE·grounding 정확도 끌어올리기

승급만으로 MAE≤5와 Kappa(grounded)≥0.60은 아직 못 맞춘다. 모델 교체와 별개로 다음을 병행하며, 본 평가에서 **착수 완료한 항목**을 함께 표기한다.

1. **grounding 프롬프트 few-shot 개선 [✔ 개선안 작성].** `is_grounded`가 +15점 premium을 좌우해 MAE를 직접 끌어올린다. 판정 기준(tech_stack·before·after 3요소)의 경계 사례를 예시로 명시한 개선 프롬프트를 `proposed_grounding_prompt.py`로 제공했다(true 1·false 3 예시, 단위 없는 표현 강제 결손). 모델을 더 키우는 건 효과 없음이 실측으로 확인됐으니(4.1 열세) **레버는 프롬프트 엔지니어링**이다. → 적용 후 `--runs 3` A/B로 효과 검증.
2. **grounding 평가셋 재균형 [✔ 완료].** grounded=True를 3/21 → **9/29**로 보강했다(`build_dataset.py`에 정량 수치가 명확한 기술 답변 6건 + 경계 False 2건 추가). 클래스 비율 14%→31%로 Kappa의 소표본 변동성을 완화했다.
3. **온도 고정·반복 측정 [✔ 도구화].** 하니스에 `--temperature`(기본 0.0=결정적)와 `--runs N`(반복 후 평균±표준편차) 옵션을 추가했다. `--runs 3 --temperature 0`으로 채점 일관성과 변동폭을 정량화한다.

### 7-3. 적용 방법

`apps/evaluation/evaluation_chains.py`의 `fetch_competency`·`fetch_grounding` 내 `model="gpt-4o-mini"`를 `"gpt-4.1-mini"`로 교체하면 된다(2곳). 설정값으로 빼두면(예: `EVAL_LLM_MODEL` 환경변수) 추후 모델 교체·A/B 비교가 쉬워진다.

---

## 8. 재현 방법

> **코드·데이터 위치:** 하니스·데이터셋·프롬프트안은 `apps/evaluation/benchmarks/`에, 본 보고서는 `docs/`에 있다. 아래 명령은 벤치마크 폴더 기준이다.

```bash
# 0) 의존성 (실호출 시에만) — OPENAI_API_KEY 는 백엔드 .env 에서 자동 로드(상위 폴더 자동 탐색)
pip install openai
cd apps/evaluation/benchmarks

# 1) 데이터셋 생성 (이미 동봉: benchmark_dataset.jsonl)
python build_dataset.py

# 2) 전체 비교 (competency + grounding, temperature=0 고정)
python llm_eval_benchmark.py --models gpt-4o-mini gpt-4.1-mini gpt-4.1 --temperature 0

# 3) 변동성 통제 — 반복 측정(평균±표준편차)
python llm_eval_benchmark.py --models gpt-4.1-mini --runs 3 --temperature 0

# 4) 호출 절감 — 핵심 기능(역량 채점)만
python llm_eval_benchmark.py --models gpt-4o-mini gpt-4.1-mini gpt-4.1 --skip-grounding

# 5) API 없이 지표 로직만 검증
python llm_eval_benchmark.py --engine mock
```

출력: `results_summary.md`(보고서 6-1 붙여넣기) · `results_summary.csv` · `results_per_answer.csv`(답변별 오차 진단).

---

## 9. 한계 및 후속 과제

- **MVP 시점 스냅샷:** 본 평가는 MVP 단계(현재 평가 파이프라인: BEI·CBI·grounding 3축 LLM 채점 + 로컬 speech)에서 수행됐다. 추후 고도화(예: SBERT 의미 유사도 축 정식 도입, 루브릭·프롬프트 개편, 가중치 재설계)가 반영되면 모델 우열·목표 달성 여부가 달라질 수 있으므로, **고도화 시점마다 본 하니스로 재측정**해 결론을 갱신해야 한다.
- **표본 규모:** 보강 후 29건으로 방향성 판단에는 충분하나 Kappa는 여전히 표본에 민감하다. 운영 로그 누적 시 50~100건으로 확장 권장.
- **Ground Truth 단일 평가자:** 현재 라벨은 담당자 1인 기준. 기획서 11-3의 "전문 면접관 Ground Truth" 정의에 맞추려면 2인 이상 라벨 후 평가자 간 Kappa로 신뢰도를 먼저 확보하는 것이 이상적.
- **Cosine 적응 적용:** 본 평가의 Cosine은 점수 프로파일 벡터 기준이며, 11-3 원문의 KR-SBERT 임베딩 정합성(Track 1)과는 측정 대상이 다르다. SBERT 축 평가는 별도 진행 필요.
- **6장 실측 표는 보강 전(21건) 기준:** 6장 수치는 21건 데이터셋으로 측정한 값이다. 평가셋 재균형(29건)·grounding 프롬프트 v2 적용 후에는 `--temperature 0 --runs 3`으로 재측정해 6장을 갱신해야 한다.

---

### 관련 파일

본 보고서: `docs/LLM_모델_성능_비교_평가서.md`
하니스·데이터·프롬프트안: `apps/evaluation/benchmarks/`

| 파일 (apps/evaluation/benchmarks/) | 설명 |
|---|---|
| `benchmark_dataset.jsonl` | 전문가 GT 라벨 **29건**(보강 후, grounded 9/20) |
| `build_dataset.py` | 데이터셋 생성기(라벨 근거 + 보강셋 aug 포함) |
| `llm_eval_benchmark.py` | 모델 비교 하니스(지표 계산 · `--temperature`/`--runs` 지원) |
| `proposed_grounding_prompt.py` | **grounding 프롬프트 few-shot 개선안**(v2) — `apps/evaluation/evaluation_prompts.py`에 적용 |
| `results_summary.md` / `*.csv` | 실행 결과(6장 = 21건 실측본, 보강셋 재측정 시 갱신) |
