# -*- coding: utf-8 -*-
"""
Career.zip 답변평가 엔진 — LLM 모델 비교용 Ground-Truth 벤치마크 데이터셋 생성기.

전문 면접관(Ground Truth) 라벨은 docs/evaluation_score_guide.md 의 채점 체계를
그대로 적용해 박은지(evaluation/report 담당)가 21개 답변에 직접 부여한 값이다.

overall_score 산출식 (guide 7절):
  technical : raw = bei_total*0.4 + cbi_score*0.4 + speech_score*0.2 + grounding_premium
  그 외     : raw = bei_total*0.5 + cbi_score*0.3 + speech_score*0.2
  grounding_premium = 15 (is_grounded=True 이고 interview_type=technical 일 때)
  final = min(raw, 100)
"""
import json

def overall(bei_total, cbi_score, speech_score, is_grounded, qtype):
    if qtype == "technical":
        prem = 15 if is_grounded else 0
        raw = bei_total * 0.4 + cbi_score * 0.4 + speech_score * 0.2 + prem
    else:
        raw = bei_total * 0.5 + cbi_score * 0.3 + speech_score * 0.2
    return round(min(raw, 100.0), 1)

def bucket(score):
    if score >= 80: return "상"
    if score >= 60: return "중"
    return "하"

# (id, session, target, order, qtype, question, answer,
#  s,t,a,r, cbi_level, speech_score, is_grounded)
ROWS = [
    # ---------------- sess_01 : senior_backend_engineer (전반적 우수) ----------------
    ("q_01_001","sess_01","senior_backend_engineer",1,"technical",
     "오픈다트 API 연동 시 대용량 트래픽과 레이트 리밋을 어떻게 해결했나?",
     "분기별 공시가 몰릴 때 API 제한 문제를 겪었고, 주도적으로 Redis 분산 락과 토큰 버킷 기반 글로벌 처리율 제한기를 구현. 병렬 파싱 속도 45% 향상, 10년치 데이터 무손실 적재.",
     22,22,24,24, 4, 100, True),
    ("q_01_002","sess_01","senior_backend_engineer",2,"technical",
     "(꼬리) 캐시 스탬피드/네트워크 병목 모니터링·방어는?",
     "확률적 조기 만료 알고리즘 설계, Prometheus+Grafana로 커넥션 풀 실시간 모니터링. 4월 공시 기간 지연 15ms 감지 후 타임아웃 200ms 튜닝으로 병목 사전 차단.",
     20,20,24,22, 4, 100, True),
    ("q_01_003","sess_01","senior_backend_engineer",3,"personality",
     "아키텍처 설계 기조 충돌 시 조율 경험은?",
     "NoSQL vs RDB 의견 대립 시 감정 대립 대신 장단점·인프라 비용 리스크 기술 비교 문서를 작성·공유. 합의 도출해 핵심 원장 RDB + 로그성 NoSQL 혼합 구조 채택.",
     22,20,23,22, 4, 100, False),
    ("q_01_004","sess_01","senior_backend_engineer",4,"job",
     "직무에서 가장 중요하게 생각하는 엔지니어링 역량은?",
     "기술 도입이 비즈니스 임팩트로 연결돼야 한다고 생각. 응답속도 개선으로 이탈률 5% 감소시킨 경험처럼 비즈니스 가치 얼라인먼트가 핵심 역량.",
     18,16,16,20, 3, 100, False),
    ("q_01_005","sess_01","senior_backend_engineer",5,"technical",
     "예상치 못한 버그/장애 극복 경험은?",
     "운영 DB 커넥션 풀 고갈 장애 발생. 슬로우 쿼리가 인덱스 미적용 풀스캔 유도하는 것 발견, 쿼리 튜닝+복합 인덱스로 CPU 90%→15% 낮추며 10분 만에 복구.",
     22,22,24,24, 4, 100, True),
    ("q_01_006","sess_01","senior_backend_engineer",6,"personality",
     "최근 깊게 학습 중인 기술 트렌드는?",
     "LLM 토큰 비용 최적화·응답속도를 위해 Vector DB 기반 검색 인프라 학습 중. 임베딩 차원 축소에 따른 검색 정확도 트레이드오프를 직접 테스트하며 회고 진행.",
     18,18,20,18, 3, 100, False),
    ("q_01_007","sess_01","senior_backend_engineer",7,"job",
     "본인이 이 프로젝트 적임자인 이유 요약은?",
     "JD 요건인 대용량 실시간 파이프라인 설계 경험과 일치하는 역량 보유. 안정적 백엔드 아키텍처로 데이터 신뢰성 책임지겠음.",
     16,14,14,16, 3, 100, False),

    # ---------------- sess_02 : data_analyst (혼재) ----------------
    ("q_02_001","sess_02","data_analyst",1,"experience",
     "올림픽 개최국 효과 분석 프로젝트 설명은?",
     "세계은행 GDP·인구 데이터로 EDA 진행. 팀원들이 정제·결측치 처리를 많이 도와줬고 시각화로 개최국 경제 성장률 상승 양상 포착. (주어가 '저희/팀원' 편중)",
     18,14,12,16, 2, 100, False),
    ("q_02_002","sess_02","data_analyst",2,"experience",
     "(꼬리) 본인이 직접 코드로 기여한 부분은?",
     "직접 맡은 부분은 세계은행 API 호출 후 판다스로 결측치 보간. 과거 5개년 평균 기반 선형 보간 스크립트 구현해 데이터 유실률 감소.",
     18,18,20,18, 3, 100, False),
    ("q_02_003","sess_02","data_analyst",3,"technical",
     "PostgreSQL 선택의 특별한 이유는?",
     "예전부터 자주 써 익숙했고 팀원들도 다 쓸 줄 알아 협업 효율 고려해 큰 고민 없이 선택. (트레이드오프/대안 비교 없음)",
     14,12,12,12, 2, 100, False),
    ("q_02_004","sess_02","data_analyst",4,"personality",
     "팀원 간 업무 배분 갈등 해결 방식은?",
     "솔직한 대화가 중요. 커피 마시며 힘든 점 편하게 털어놓고 조율하면 대부분 원만히 해결됐던 것 같음.",
     16,14,16,14, 2, 100, False),
    ("q_02_005","sess_02","data_analyst",5,"technical",
     "BI 툴 대신 파이썬 시각화 라이브러리를 고집한 이유는?",
     "BI 툴 라이선스 비용 부담이 있었고 분석 템플릿 재사용을 위해 Matplotlib+Seaborn 조합 자동화 리포트 파이프라인 구축이 낫다고 판단.",
     18,18,18,16, 3, 100, False),
    ("q_02_006","sess_02","data_analyst",6,"job",
     "마이그레이션 중 데이터 사고 대처 방안은?",
     "일단 상급자 즉시 보고·공유, 미리 만들어둔 백업 스냅샷으로 안전하게 롤백 진행.",
     16,16,16,16, 2, 100, False),
    ("q_02_007","sess_02","data_analyst",7,"job",
     "분석가로서 본인만의 핵심 강점은?",
     "데이터 겉모습만 보지 않고 지표의 비즈니스 영향력을 끝까지 추적하는 성실함과 끈기가 가장 큰 무기.",
     16,14,14,16, 2, 100, False),

    # ---------------- sess_03 : ml_data_engineer (전반적 미흡, 필러 과다) ----------------
    ("q_03_001","sess_03","ml_data_engineer",1,"technical",
     "데이터 파이프라인 규모와 정량적 성과는?",
     "어... 그니까... 데이터가 엄청 많았는데요. 음... 그냥 매일 들어오는 데이터를 안정적으로 돌렸고 성능도 빨라졌다고 다들 좋아하셨음. 구체적 수치는 기억 안 남.",
     12,10,10,10, 1, 60, False),
    ("q_03_002","sess_03","ml_data_engineer",2,"technical",
     "(꼬리) 처리량/지연 수치 범위라도 말해달라",
     "음... 어... 정확히 기억은 안 나는데 체감상 전보다 시스템이 안 멈추고 부드럽게 굴러갔던 것 같음. 동시 접속자 많아도 끄떡없었음.",
     10,10,8,8, 1, 65, False),
    ("q_03_003","sess_03","ml_data_engineer",3,"job",
     "입사 후 다루고 싶은 JD상 핵심 모델 레이어는?",
     "사실 딥러닝보다 프론트엔드 UI 디자인이나 간단한 웹 서비스 페이지 만드는 작업에 흥미가 많음. 풀스택 업무를 다 해보고 싶음. (ML JD와 불일치)",
     12,10,10,10, 1, 85, False),
    ("q_03_004","sess_03","ml_data_engineer",4,"personality",
     "마감 촉박·진척 부진 시 행동은?",
     "기한 촉박하면 팀장님이 일정 미뤄주거나 위에서 대책 세워줄 테니 맡은 루틴 일만 묵묵히 하며 결과 기다렸음. (수동적)",
     12,10,8,10, 1, 90, False),
    ("q_03_005","sess_03","ml_data_engineer",5,"personality",
     "다른 파트 개발자가 소통을 거부하면?",
     "굳이 소통 피하는 사람에게 억지로 다가가고 싶지 않음. 이메일로 서류상 넘기고 내 할 일만 끝내겠음.",
     10,8,8,8, 1, 100, False),
    ("q_03_006","sess_03","ml_data_engineer",6,"technical",
     "하둡(Hadoop)의 단점은?",
     "어... 하둡이요? 수업 시간에 좋다고 해서 대충 설치만 해봤고 단점·한계는 깊게 생각 안 해봐서 잘 모르겠음.",
     10,8,8,8, 1, 95, False),
    ("q_03_007","sess_03","ml_data_engineer",7,"job",
     "채용되어야 하는 단 하나의 이유는?",
     "그냥 시키는 대로 무조건 성실하게 군말 없이 군대식으로 잘 다닐 수 있음. 뽑아만 주십시오.",
     10,8,8,10, 1, 95, False),

    # ---------------- 보강셋(aug): grounded 클래스 불균형 완화용 (technical) ----------------
    # grounded=True: tech_stack + before_metric + after_metric 3요소 모두 명확
    ("q_aug_01","aug","backend_engineer",1,"technical",
     "결제 조회 API 성능을 어떻게 개선했나?",
     "결제 조회 API 평균 응답이 1.2초였는데, Redis로 키 단위 TTL 캐시를 적용해 180ms로 약 85% 단축했습니다.",
     20,20,23,23, 3, 100, True),
    ("q_aug_02","aug","backend_engineer",2,"technical",
     "검색 지연을 줄인 경험은?",
     "Elasticsearch 색인 구조를 nested에서 flatten으로 변경해 검색 p95 지연을 900ms에서 220ms로 줄였습니다.",
     20,20,22,22, 3, 100, True),
    ("q_aug_03","aug","backend_engineer",3,"technical",
     "비동기 처리량을 높인 방법은?",
     "Celery 워커 prefetch를 4에서 1로 낮추고 큐를 우선순위별로 분리해 처리량을 시간당 1.2만 건에서 3.5만 건으로 올렸습니다.",
     18,18,22,22, 3, 100, True),
    ("q_aug_04","aug","backend_engineer",4,"technical",
     "N+1 쿼리 문제를 어떻게 해결했나?",
     "목록 API의 N+1을 select_related/prefetch_related로 제거해 쿼리 수를 320개에서 6개로, 응답을 2.4초에서 0.3초로 줄였습니다.",
     20,20,23,23, 4, 100, True),
    ("q_aug_05","aug","backend_engineer",5,"technical",
     "동시성 처리를 개선한 사례는?",
     "Gunicorn 워커를 sync에서 gevent로 전환하고 워커 수를 튜닝해 RPS를 150에서 600으로 4배 향상시켰습니다.",
     18,18,20,22, 3, 100, True),
    ("q_aug_06","aug","backend_engineer",6,"technical",
     "파일 업로드 성능 개선 경험은?",
     "이미지 업로드를 S3 멀티파트 업로드와 CloudFront로 전환해 평균 업로드 시간을 8초에서 2.1초로, 실패율을 3%에서 0.2%로 낮췄습니다.",
     18,18,20,22, 3, 100, True),
    # grounded=False 경계 사례: 기술명은 있으나 정량 수치(before/after) 결손
    ("q_aug_07","aug","backend_engineer",7,"technical",
     "캐싱 도입 효과는?",
     "Redis를 도입해 캐싱을 적용했고 확실히 더 빨라졌습니다. 사용자 반응도 좋았습니다.",
     16,14,16,12, 2, 100, False),
    ("q_aug_08","aug","backend_engineer",8,"technical",
     "응답 속도 문제를 어떻게 다뤘나?",
     "기존에 응답이 느려서 문제였는데 인덱스를 추가해서 많이 개선했습니다.",
     14,12,14,12, 2, 100, False),
]

records = []
for (rid, sess, target, order, qtype, q, a, s, t, ac, r, cbi_level, speech, grounded) in ROWS:
    bei_total = s + t + ac + r
    cbi_score = cbi_level * 20
    ov = overall(bei_total, cbi_score, speech, grounded, qtype)
    records.append({
        "id": rid,
        "session_id": sess,
        "evaluation_target": target,
        "order_index": order,
        "interview_type": qtype,
        "question_text": q,
        "answer_text": a,
        "ground_truth": {
            "bei": {"situation": s, "task": t, "action": ac, "result": r, "total": bei_total},
            "cbi_level": cbi_level,
            "cbi_score": cbi_score,
            "speech_score": speech,
            "is_grounded": grounded,
            "overall_score": ov,
            "quality_bucket": bucket(ov),
        },
    })

with open("benchmark_dataset.jsonl", "w", encoding="utf-8") as f:
    for rec in records:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

# 요약 출력
import statistics as st
scores = [r["ground_truth"]["overall_score"] for r in records]
grounded_n = sum(r["ground_truth"]["is_grounded"] for r in records)
print(f"총 {len(records)}개 답변")
print(f"overall_score: min={min(scores)} max={max(scores)} mean={round(st.mean(scores),1)} std={round(st.pstdev(scores),1)}")
print(f"is_grounded=True: {grounded_n} / False: {len(records)-grounded_n}")
for sess in ("sess_01","sess_02","sess_03","aug"):
    ss = [r["ground_truth"]["overall_score"] for r in records if r["session_id"]==sess]
    print(f"  {sess}: {ss}")
# end of build_dataset.py
