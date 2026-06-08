import json
from openai import OpenAI


def calculate_match_score(
    jd_keywords: list[str],
    resume_analysis: dict,
    cover_letter_text: str = "",
) -> dict:
    """
    JD 키워드와 이력서 분석 결과를 비교해 매칭 점수·강점·약점·자소서 포인트 반환.

    반환 형식:
    {
        "match_score": 87.5,
        "strengths":   ["강점1", "강점2"],
        "weaknesses":  ["약점1", "약점2"],
        "cl_points":   ["자소서 반영 포인트1", "포인트2"]
    }
    """
    client = OpenAI()

    tech_stack   = resume_analysis.get("tech_stack", [])
    experiences  = resume_analysis.get("key_experiences", [])
    strengths    = resume_analysis.get("strengths", [])
    projects     = resume_analysis.get("projects", [])

    proj_str = "\n".join(
        f"- {p['name']}: {p.get('role', '')} / 기술: {', '.join(p.get('tech', []))} / 성과: {p.get('result', '')}"
        for p in projects
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        messages=[
            {
                "role": "system",
                "content": (
                    "당신은 IT 직무 채용 매칭 전문가입니다.\n"
                    "JD 요구사항과 지원자 이력서를 비교 분석해 매칭 점수와 피드백을 제공합니다.\n\n"
                    "분석 기준:\n"
                    "1. match_score: JD 키워드 대비 이력서 기술 스택 커버리지 (0.0 ~ 100.0)\n"
                    "2. strengths: JD 요구사항과 일치하는 지원자의 강점 (최대 5개)\n"
                    "3. weaknesses: JD에서 요구하지만 이력서에 부족한 역량 (최대 5개)\n"
                    "4. cl_points: 자소서에서 면접에 활용할 수 있는 핵심 포인트 (최대 3개)\n\n"
                    "반드시 아래 JSON 형식으로만 응답하세요. 마크다운 블록 금지.\n"
                    "{\n"
                    '  "match_score": 87.5,\n'
                    '  "strengths":  ["강점1", "강점2"],\n'
                    '  "weaknesses": ["약점1", "약점2"],\n'
                    '  "cl_points":  ["포인트1", "포인트2"]\n'
                    "}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"[JD 핵심 키워드]\n{', '.join(jd_keywords)}\n\n"
                    f"[지원자 기술 스택]\n{', '.join(tech_stack)}\n\n"
                    f"[핵심 경험]\n" + "\n".join(f"- {e}" for e in experiences) + "\n\n"
                    f"[강점]\n" + "\n".join(f"- {s}" for s in strengths) + "\n\n"
                    f"[프로젝트]\n{proj_str}\n\n"
                    f"[자기소개서 요약]\n{cover_letter_text[:500] if cover_letter_text else '미입력'}\n\n"
                    "위 정보를 바탕으로 JD 매칭 분석을 해주세요."
                ),
            },
        ],
    )

    raw = response.choices[0].message.content.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)
