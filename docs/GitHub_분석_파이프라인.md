# GitHub 분석 파이프라인 기준

작성 기준: 2026-06-18

## 컬럼별 의미

| 컬럼 | 의미 | 분석 대상 기본 포함 |
| --- | --- | --- |
| `input_userprofile.github_url` | 사용자 대표 GitHub 프로필 URL | 아니오 |
| `input_resumemaster.github_url` | 선택 이력서의 대표/참고 GitHub URL | project URL이 없을 때만 fallback 검토 |
| `input_projectexperience.github_url` | 개별 프로젝트 Repository URL | 예, 최우선 |

## 조회 우선순위

```text
1. input_projectexperience.github_url
2. input_resumemaster.github_url
3. input_userprofile.github_url은 사용자가 명시적으로 분석 대상으로 선택한 경우만 사용
```

프로필 URL이 단순 `https://github.com/{username}` 형태라면 Repository URL로 간주하지 않는다.

## 다중 Repository

`github_url` 한 컬럼에 `URL1,URL2` 또는 `URL1|URL2` 형태로 저장하지 않는다. 여러 Repository는 `ProjectExperience` row 여러 건으로 관리한다.

## 현재 구현과 승인 필요점

현재 `ProjectExperience`는 `User`에만 연결되어 있고 `ResumeMaster` FK가 없다. 질문 생성 서비스는 현재 `session.user.projects.all()`을 읽을 수 있어 복수 이력서 상황에서 선택 이력서와 프로젝트 매핑을 확정할 수 없다.

승인 전에는 다음을 구현하지 않는다.

```text
ProjectExperience -> ResumeMaster FK 추가
ResumeProjectMapping 중간 테이블 추가
면접 세션에 선택 프로젝트 저장
프로필 GitHub URL 자동 분석 대상 포함
```
