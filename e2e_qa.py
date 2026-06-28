"""
E2E QA 스크립트 — Career.zip Report API
실행: python e2e_qa.py

테스트 계정: test_report@career.zip / Test1234!
세션 UUID:   699864cf-551e-4f1a-b921-a8249d75f198
"""
import json
import sys
import requests

BASE = "http://127.0.0.1:8000/api/v1"
EMAIL = "test_report@career.zip"
PASSWORD = "Test1234!"
SESSION_UUID = "699864cf-551e-4f1a-b921-a8249d75f198"

OK = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
SKIP = "\033[93m-\033[0m"

results = []

def check(label, cond, detail=""):
    icon = OK if cond else FAIL
    print(f"  {icon} {label}" + (f"  →  {detail}" if detail else ""))
    results.append((label, cond))

def pretty(data):
    return json.dumps(data, ensure_ascii=False, indent=2)[:400]


# ── 1. 로그인 ────────────────────────────────────────────
print("\n[1] 로그인")
r = requests.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD})
check("POST /accounts/login/ → 200", r.status_code == 200, f"status={r.status_code}")
if r.status_code != 200:
    print(f"     응답: {r.text[:200]}")
    sys.exit(1)

token = r.json().get("access") or r.json().get("access_token")
check("access token 존재", bool(token))
if not token:
    sys.exit(1)

headers = {"Authorization": f"Bearer {token}"}
print(f"  token prefix: {token[:30]}...")


# ── 2. /sessions/latest/report ───────────────────────────
print("\n[2] GET /sessions/latest/report  (신규 엔드포인트)")
r = requests.get(f"{BASE}/sessions/latest/report", headers=headers)
check("status 200", r.status_code == 200, f"status={r.status_code}")
if r.status_code == 200:
    body = r.json()
    summary = body.get("summary", {})
    meta = summary.get("evaluation_metadata", {})
    score = summary.get("score_summary", {})
    check("summary 존재", bool(summary))
    check("evaluation_metadata.session_id 존재", bool(meta.get("session_id")))
    check("score_summary.overall_score 존재", score.get("overall_score") is not None,
          f"score={score.get('overall_score')}")
    check("dynamically_triggered_tags 존재", "dynamically_triggered_tags" in summary)
    check("summary_text raw 태그 키 없음 (버그 수정 검증)",
          not str(summary.get("evaluation_metadata", {}).get("summary_text", "")).startswith("["),
          meta.get("summary_text", "")[:60])
else:
    print(f"     응답: {r.text[:300]}")


# ── 3. /sessions/{uuid}/report ───────────────────────────
print(f"\n[3] GET /sessions/{SESSION_UUID}/report")
r = requests.get(f"{BASE}/sessions/{SESSION_UUID}/report", headers=headers)
check("status 200", r.status_code == 200, f"status={r.status_code}")
if r.status_code == 200:
    body = r.json()
    summary = body.get("summary", {})
    meta = summary.get("evaluation_metadata", {})
    detail = summary.get("score_detail", {})
    questions = detail.get("questions", [])
    check("session_id 일치", meta.get("session_id") == SESSION_UUID,
          meta.get("session_id"))
    check("score_detail.questions 존재", isinstance(questions, list),
          f"count={len(questions)}")
    if questions:
        q = questions[0]
        check("질문별 필드 완전성 (question_text, score, improvement_action)",
              all(k in q for k in ("question_text", "score", "improvement_action")))
    check("speech_diagnostics 존재", "speech_diagnostics" in detail)
else:
    print(f"     응답: {r.text[:300]}")


# ── 4. 타 유저 세션 접근 차단 (소유권 검증) ──────────────
print("\n[4] 소유권 검증 — 없는 세션 UUID로 접근")
r = requests.get(f"{BASE}/sessions/00000000-0000-0000-0000-000000000000/report", headers=headers)
check("존재하지 않는 session → 404", r.status_code == 404, f"status={r.status_code}")


# ── 5. 인증 없이 접근 차단 ────────────────────────────────
print("\n[5] 인증 없이 접근 차단")
r = requests.get(f"{BASE}/sessions/latest/report")
check("/sessions/latest/report 비인증 → 401", r.status_code == 401, f"status={r.status_code}")


# ── 결과 요약 ────────────────────────────────────────────
print("\n" + "─" * 50)
passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"결과: {passed}/{total} passed")
if passed < total:
    print("실패 항목:")
    for label, ok in results:
        if not ok:
            print(f"  {FAIL} {label}")
