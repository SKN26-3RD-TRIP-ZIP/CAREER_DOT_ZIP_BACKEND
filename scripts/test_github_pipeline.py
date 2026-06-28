"""
GitHub 분석 파이프라인 수동 테스트 스크립트
============================================
각 단계를 순서대로 실행하고 중간 결과를 출력한다.
Django 없이 순수 함수 단계는 즉시 실행 가능하고,
API 연동 단계는 환경변수(GITHUB_TOKEN, OPENAI_API_KEY)가 필요하다.

실행 방법:
    # 환경변수 설정 후 Django 없이 순수 함수 단계만 실행
    python scripts/test_github_pipeline.py --dry

    # 전체 파이프라인 (GITHUB_TOKEN + OPENAI_API_KEY 필요)
    DJANGO_SETTINGS_MODULE=config.settings.local python scripts/test_github_pipeline.py

    # 특정 repo 지정
    DJANGO_SETTINGS_MODULE=config.settings.local python scripts/test_github_pipeline.py \\
        --url https://github.com/<owner>/<repo>
"""

import argparse
import json
import os
import sys
import textwrap

# ── 경로 설정 ────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

STEP_OK   = "✅"
STEP_SKIP = "⏭ "
STEP_FAIL = "❌"
SEP       = "─" * 60


def _header(title: str):
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print('═' * 60)


def _sub(label: str, value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, indent=2)
    lines = str(value).splitlines()
    first = lines[0] if lines else ""
    rest  = lines[1:] if len(lines) > 1 else []
    print(f"  {label:<22}: {first}")
    for l in rest:
        print(f"  {' ' * 24}{l}")


# ════════════════════════════════════════════════════════════
# STEP 1 — URL 파싱 (순수 함수, 네트워크 없음)
# ════════════════════════════════════════════════════════════

def step1_url_parse(url: str):
    _header("STEP 1 — URL 파싱 (parse_repo_url)")
    from apps.analysis.services.github_service import parse_repo_url
    try:
        owner, repo = parse_repo_url(url)
        print(f"  {STEP_OK}  owner={owner!r}  repo={repo!r}")
        return owner, repo
    except ValueError as e:
        print(f"  {STEP_FAIL} {e}")
        sys.exit(1)


# ════════════════════════════════════════════════════════════
# STEP 2 — 매니페스트 + README 수집 (analyze_repo 내부: fetch_manifests)
# ════════════════════════════════════════════════════════════

def step2_fetch(url: str):
    _header("STEP 2 — GitHub API 호출 (analyze_repo)")
    from apps.analysis.services.github_service import analyze_repo
    print(f"  URL: {url}")
    result = analyze_repo(url)

    if not result["ok"]:
        print(f"  {STEP_FAIL} error_kind={result['error_kind']}  msg={result['error']}")
        return None

    print(f"  {STEP_OK} 기본 분기: {result.get('default_branch', '?')}")
    _sub("언어 통계",      result["languages"])
    _sub("검출 프레임워크", result["frameworks"])
    _sub("근거 패키지 수",  len(result["raw_packages"]))

    readme = result.get("readme", "")
    print(f"\n  README 원문 길이: {len(readme)}자")
    if readme:
        print(f"  README 앞 300자:\n{textwrap.indent(readme[:300], '    ')}")
    else:
        print(f"  {STEP_FAIL} README 없음")

    return result


# ════════════════════════════════════════════════════════════
# STEP 3 — README 노이즈 제거 (순수 함수, 네트워크 없음)
# ════════════════════════════════════════════════════════════

def step3_clean_readme(raw_readme: str):
    _header("STEP 3 — README 전처리 (preprocess_readme + _deep_clean_readme)")
    from apps.analysis.services.github_service import preprocess_readme, _deep_clean_readme

    step1_out = preprocess_readme(raw_readme)
    print(f"  {STEP_OK} preprocess_readme 후: {len(step1_out)}자")

    step2_out = _deep_clean_readme(step1_out, max_chars=8000)
    print(f"  {STEP_OK} _deep_clean_readme 후: {len(step2_out)}자")

    print(f"\n  정제된 README (앞 500자):\n{textwrap.indent(step2_out[:500], '    ')}")
    return step2_out


# ════════════════════════════════════════════════════════════
# STEP 4 — LLM JSON 추출 (gpt-4o-mini)
# ════════════════════════════════════════════════════════════

def step4_llm_extract(cleaned_readme: str, frameworks: list):
    _header("STEP 4 — LLM 면접 컨텍스트 추출 (gpt-4o-mini)")

    # Django settings가 없으면 스킵
    if not os.getenv("DJANGO_SETTINGS_MODULE"):
        print(f"  {STEP_SKIP} DJANGO_SETTINGS_MODULE 미설정 — LLM 단계 스킵")
        return None

    try:
        import django
        django.setup()
    except Exception as e:
        print(f"  {STEP_SKIP} Django 초기화 실패 ({e}) — LLM 단계 스킵")
        return None

    from apps.analysis.services.utils import get_client, clean_json

    prompt = (
        "당신은 IT 채용 면접 코치입니다.\n"
        "아래는 GitHub 프로젝트의 README입니다.\n"
        "면접관이 이 프로젝트를 보고 질문할 만한 내용만 추출해주세요.\n"
        "설치 방법, 라이선스, 기여 가이드, 배지, 실행 명령어는 완전히 무시하세요.\n\n"
        "반드시 아래 JSON 형식으로만 응답하세요.\n\n"
        '{\n'
        '  "project_name": "프로젝트 이름",\n'
        '  "project_overview": "2~3문장 설명, 없으면 null",\n'
        '  "tech_stack": ["사용 기술"],\n'
        '  "my_role": "역할, 없으면 null",\n'
        '  "key_features": ["핵심 기능, 최대 5개"],\n'
        '  "technical_challenges": ["트러블슈팅, 없으면 빈 배열"],\n'
        '  "architecture": "구조 설명, 없으면 null",\n'
        '  "interview_points": ["면접 포인트, 최대 3개"]\n'
        '}\n\n'
        f"README:\n{cleaned_readme}"
    )

    client = get_client()
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.choices[0].message.content
        data = json.loads(clean_json(raw))
        print(f"  {STEP_OK} LLM 응답 파싱 성공")
        _sub("project_name",          data.get("project_name"))
        _sub("project_overview",      data.get("project_overview"))
        _sub("tech_stack (LLM)",      data.get("tech_stack"))
        _sub("my_role",               data.get("my_role"))
        _sub("key_features",          data.get("key_features"))
        _sub("technical_challenges",  data.get("technical_challenges"))
        _sub("architecture",          data.get("architecture"))
        _sub("interview_points",      data.get("interview_points"))
        return data
    except json.JSONDecodeError as e:
        print(f"  {STEP_FAIL} JSON 파싱 실패: {e}")
        print(f"  LLM 원문:\n{textwrap.indent(raw[:400], '    ')}")
        return None
    except Exception as e:
        print(f"  {STEP_FAIL} LLM 호출 실패: {e}")
        return None


# ════════════════════════════════════════════════════════════
# STEP 5 — tech_stack 합집합 병합 (순수 함수)
# ════════════════════════════════════════════════════════════

def step5_merge_tech(repo_frameworks: list, llm_data: dict | None):
    _header("STEP 5 — tech_stack 병합 (analyze_repo + LLM 합집합)")
    if llm_data is None:
        print(f"  {STEP_SKIP} LLM 결과 없음 — 병합 스킵")
        return

    llm_tech = llm_data.get("tech_stack") or []
    merged   = sorted(set(repo_frameworks) | set(llm_tech))
    print(f"  analyze_repo frameworks: {repo_frameworks}")
    print(f"  LLM tech_stack:          {llm_tech}")
    print(f"  {STEP_OK} 병합 결과: {merged}")
    return merged


# ════════════════════════════════════════════════════════════
# STEP 6 — 컨텍스트 문자열 조립 (views.py 로직과 동일)
# ════════════��═══════════════════════════════════════════════

def step6_build_context(github_summary: dict | None):
    _header("STEP 6 — 컨텍스트 문자열 조립 (views.py와 동일 로직)")
    if not github_summary:
        print(f"  {STEP_SKIP} github_summary 없음 — github_context = ''")
        return ""

    lines = ["=== GitHub 프로젝트 기반 추가 컨텍스트 ==="]
    if github_summary.get("project_name"):
        lines.append(f"프로젝트명: {github_summary['project_name']}")
    if github_summary.get("project_overview"):
        lines.append(f"개요: {github_summary['project_overview']}")
    if github_summary.get("tech_stack"):
        lines.append(f"기술 스택: {', '.join(github_summary['tech_stack'])}")
    if github_summary.get("key_features"):
        lines.append("핵심 기능:")
        lines.extend([f"  - {f}" for f in github_summary["key_features"]])
    if github_summary.get("technical_challenges"):
        lines.append("기술적 도전:")
        lines.extend([f"  - {c}" for c in github_summary["technical_challenges"]])
    if github_summary.get("architecture"):
        lines.append(f"아키텍처: {github_summary['architecture']}")
    if github_summary.get("interview_points"):
        lines.append("면접 포인트:")
        lines.extend([f"  - {p}" for p in github_summary["interview_points"]])
    lines.append("==========================================")
    context = "\n".join(lines)

    print(f"  {STEP_OK} 컨텍스트 조립 완료 ({len(context)}자)")
    print(f"\n  ─── 생성된 github_context ───")
    print(textwrap.indent(context, "  "))
    return context


# ════════════════════════════════════════════════════════════
# STEP 7 — extract_interview_context() 통합 테스트
# ════════════════════════════════════════════════════════════

def step7_full_pipeline(url: str):
    _header("STEP 7 — extract_interview_context() 통합 실행")

    if not os.getenv("DJANGO_SETTINGS_MODULE"):
        print(f"  {STEP_SKIP} DJANGO_SETTINGS_MODULE 미설정 — 통합 단계 스킵")
        return

    try:
        import django
        django.setup()
    except Exception as e:
        print(f"  {STEP_SKIP} Django 초기화 실패 ({e})")
        return

    from apps.analysis.services.github_service import extract_interview_context
    print(f"  URL: {url}")
    result = extract_interview_context(url)

    print(f"\n  ok: {result['ok']}")
    if result["ok"]:
        print(f"  {STEP_OK} 성공")
        print(f"\n  최종 반환 data:")
        print(textwrap.indent(json.dumps(result["data"], ensure_ascii=False, indent=2), "  "))
    else:
        print(f"  {STEP_FAIL} error_code: {result['error_code']}")


# ════════════════════════════════════════════════════════════
# 순수 함수 단위 검증 (--dry 모드)
# ════════════════════════════════════════════════════════════

def run_dry_tests():
    _header("DRY 모드 — 순수 함수 단위 검증 (네트워크/LLM 없음)")

    from apps.analysis.services.github_service import (
        parse_repo_url, is_dependency_file,
        extract_dependencies, preprocess_readme, _deep_clean_readme,
    )

    # URL 파싱
    cases = [
        ("https://github.com/owner/my-repo",          ("owner", "my-repo")),
        ("https://github.com/owner/repo.git",          ("owner", "repo")),
        ("https://github.com/owner/repo/tree/main",    ("owner", "repo")),
    ]
    passed = failed = 0
    for url, expected in cases:
        try:
            got = parse_repo_url(url)
            ok = got == expected
        except ValueError:
            ok = False
        if ok:
            print(f"  {STEP_OK} parse_repo_url({url!r}) → {got}")
            passed += 1
        else:
            print(f"  {STEP_FAIL} parse_repo_url({url!r}) → expected {expected}")
            failed += 1

    # 의존성 추출 샘플
    files = {
        "requirements.txt": "Django==4.2\ndjangorestframework>=3.14\ncelery\n",
        "package.json":     '{"dependencies":{"react":"^18","next":"14.0"}}',
    }
    result = extract_dependencies(files)
    expected_fw = {"Django", "Django REST Framework", "Celery", "React", "Next.js"}
    got_fw = set(result["frameworks"])
    if expected_fw == got_fw:
        print(f"  {STEP_OK} extract_dependencies → {sorted(got_fw)}")
        passed += 1
    else:
        print(f"  {STEP_FAIL} extract_dependencies: 기대={sorted(expected_fw)} 실제={sorted(got_fw)}")
        failed += 1

    # README 전처리
    raw = "# 프로젝트\n설명입니다.\n```bash\npip install x\n```\n## License\nMIT"
    cleaned = _deep_clean_readme(preprocess_readme(raw))
    shield_removed = "shields.io" not in cleaned
    install_removed = "pip install" not in cleaned
    license_removed = "MIT" not in cleaned
    desc_kept = "설명입니다" in cleaned
    all_ok = shield_removed and install_removed and license_removed and desc_kept
    if all_ok:
        print(f"  {STEP_OK} README 전처리 — 노이즈 제거 + 설명 유지 확인")
        passed += 1
    else:
        print(f"  {STEP_FAIL} README 전처리 실패 (desc_kept={desc_kept}, install_removed={install_removed}, license_removed={license_removed})")
        failed += 1

    print(f"\n  결과: {passed}개 통과 / {failed}개 실패")


# ════════════════════════════════════════════════════════════
# main
# ════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="GitHub 파이프라인 단계별 테스트")
    parser.add_argument("--url", default="https://github.com/pallets/flask",
                        help="테스트할 GitHub repo URL (기본: pallets/flask)")
    parser.add_argument("--dry", action="store_true",
                        help="네트워크/LLM 없이 순수 함수만 검증")
    args = parser.parse_args()

    print(f"\n{'═' * 60}")
    print(f"  GitHub 분석 파이프라인 테스트")
    print(f"  URL: {args.url}")
    print(f"  GITHUB_TOKEN: {'설정됨' if os.getenv('GITHUB_TOKEN') else '미설정 (rate limit 주의)'}")
    print(f"  OPENAI_API_KEY: {'설정됨' if os.getenv('OPENAI_API_KEY') else '미설정'}")
    print(f"{'═' * 60}")

    if args.dry:
        run_dry_tests()
        return

    # 전체 파이프라인 단계별 실행
    step1_url_parse(args.url)
    repo_result = step2_fetch(args.url)
    if repo_result is None:
        print("\n⛔ STEP 2 실패 — 이후 단계 중단")
        sys.exit(1)

    cleaned = step3_clean_readme(repo_result.get("readme", ""))
    llm_data = step4_llm_extract(cleaned, repo_result.get("frameworks", []))
    merged   = step5_merge_tech(repo_result.get("frameworks", []), llm_data)

    # LLM 결과가 있으면 tech_stack 업데이트
    if llm_data and merged:
        llm_data["tech_stack"] = merged

    step6_build_context(llm_data)
    step7_full_pipeline(args.url)

    print(f"\n{'═' * 60}")
    print("  테스트 완료")
    print(f"{'═' * 60}\n")


if __name__ == "__main__":
    main()
