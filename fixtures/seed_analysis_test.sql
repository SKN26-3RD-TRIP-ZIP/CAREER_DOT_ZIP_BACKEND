-- ============================================================
--  JD 분석 테스트용 시드 데이터
--  테스트 계정: test.dev@career.zip / test1234!
--  실행 순서: user → profile → jd → resume → cover_letter → cover_letter_item
-- ============================================================

-- ① 유저 (accounts_user)
--    마이그레이션 기준 필드:
--    id(BigAutoField), password, last_login, is_superuser,
--    email, name, is_verified, status, role,
--    is_staff, is_active, created_at, updated_at
--    + groups/user_permissions 는 별도 중간 테이블이므로 INSERT 불필요
INSERT INTO accounts_user (
    password,
    last_login,
    is_superuser,
    email,
    name,
    is_verified,
    status,
    role,
    is_staff,
    is_active,
    created_at,
    updated_at
) VALUES (
    'pbkdf2_sha256$600000$P0TE2rKEZQ19cmleUvbgEv$oZs6LM7S4Vv8K4ZH37ZljLMH2uE6wXb3zM2HeGwLG5k=',
    NULL,
    0,
    'test.dev@career.zip',
    '김테스트',
    1,
    'active',
    'user',
    0,
    1,
    NOW(),
    NOW()
);

-- 방금 생성된 user_id 저장
SET @user_id = LAST_INSERT_ID();

-- UUID 미리 고정 (이후 FK에서 재사용)
SET @jd_uuid           = UUID();
SET @resume_uuid       = UUID();
SET @cl_uuid           = UUID();
SET @cl_item1_uuid     = UUID();
SET @cl_item2_uuid     = UUID();
SET @profile_uuid      = UUID();

-- ② 유저 프로필 (input_userprofile)
--    필드: id(UUID), user_id, career_type, major_type,
--          desired_job, career_year, github_url, created_at, updated_at
INSERT INTO input_userprofile (
    id,
    user_id,
    career_type,
    major_type,
    desired_job,
    career_year,
    github_url,
    created_at,
    updated_at
) VALUES (
    @profile_uuid,
    @user_id,
    '경력',
    '전공',
    '백엔드 개발자',
    2,
    'https://github.com/kim-test',
    NOW(),
    NOW()
);

-- ③ JD (input_jobdescription)
--    필드: id(UUID), user_id, company_name, position, original_text,
--          input_method, company_summary, talent_profile,
--          job_requirements, keywords, analysis_status,
--          created_at, updated_at
INSERT INTO input_jobdescription (
    id,
    user_id,
    company_name,
    position,
    original_text,
    input_method,
    company_summary,
    talent_profile,
    job_requirements,
    keywords,
    analysis_status,
    created_at,
    updated_at
) VALUES (
    @jd_uuid,
    @user_id,
    '테크스타트업',
    'Python 백엔드 개발자',
    '[포지션]\nPython 백엔드 개발자 (경력 3년 이상)\n\n[주요 업무]\n- Django/DRF 기반 REST API 설계 및 개발\n- Redis를 활용한 캐싱 전략 수립 및 성능 최적화\n- Kubernetes 클러스터 위에서 서비스 배포 및 운영\n- Kafka를 통한 이벤트 기반 비동기 처리 파이프라인 구축\n- PostgreSQL 쿼리 최적화 및 인덱스 설계\n\n[자격 요건]\n- Python, Django 실무 경험 3년 이상\n- Redis 캐싱 실무 적용 경험\n- REST API 설계 원칙 이해 및 실무 경험\n- 대졸 이상\n\n[우대 사항]\n- Kubernetes 컨테이너 오케스트레이션 실무 경험\n- Kafka 메시지 큐 실무 경험\n- 주도적으로 문제를 발견하고 개선안을 제안한 경험\n\n[기술 스택]\nPython, Django, DRF, Redis, Kubernetes, Kafka, PostgreSQL, Docker',
    'TEXT',
    NULL,
    NULL,
    'Python, Django 실무 경험 3년 이상 / Redis 캐싱 실무 적용 / 대졸 이상',
    NULL,
    'PENDING',
    NOW(),
    NOW()
);

-- ④ 이력서 (input_resumemaster)
--    필드: id(UUID), user_id, name, phone, email, address,
--          github_url, original_text, extracted_keywords,
--          is_active, created_at, updated_at
INSERT INTO input_resumemaster (
    id,
    user_id,
    name,
    phone,
    email,
    address,
    github_url,
    original_text,
    extracted_keywords,
    is_active,
    created_at,
    updated_at
) VALUES (
    @resume_uuid,
    @user_id,
    '김테스트 이력서',
    '010-1234-5678',
    'test.dev@career.zip',
    NULL,
    'https://github.com/kim-test',
    '[경력]\n2024.03 ~ 현재  (주)배달플랫폼 | 백엔드 개발자\n- Django/DRF 기반 주문·정산 API 개발 및 유지보수\n- Redis 캐싱 전략 도입으로 API 응답 속도 40% 개선\n- PostgreSQL 쿼리 최적화로 DB 조회 속도 30% 향상\n- GitHub Actions 기반 CI/CD 파이프라인 구축\n- 팀 코드 리뷰 프로세스 도입 주도\n\n2022.07 ~ 2024.02  (주)이커머스솔루션 | 주니어 백엔드 개발자\n- Django REST Framework로 상품·재고 관리 API 개발\n- PostgreSQL 마이그레이션 참여\n- Docker 기반 로컬 개발 환경 표준화\n\n[기술 스택]\n언어: Python\n프레임워크: Django, Django REST Framework\nDB: PostgreSQL, Redis\n인프라: Docker, GitHub Actions\n\n[학력]\nOO대학교 컴퓨터공학과 졸업 (2022.02)\n\n[프로젝트]\n배달 플랫폼 주문 API\n- Django/DRF, Redis, PostgreSQL\n- Redis TTL 전략으로 응답 속도 40% 개선\n- 주문 상태 FSM 설계 및 정산 배치 API 구현',
    NULL,
    1,
    NOW(),
    NOW()
);

-- ⑤ 자소서 (input_coverletter)
--    필드: id(UUID), user_id, jd_id, title, company_name,
--          is_active, created_at, updated_at
INSERT INTO input_coverletter (
    id,
    user_id,
    jd_id,
    title,
    company_name,
    is_active,
    created_at,
    updated_at
) VALUES (
    @cl_uuid,
    @user_id,
    @jd_uuid,
    '테크스타트업 백엔드 개발자 자기소개서',
    '테크스타트업',
    1,
    NOW(),
    NOW()
);

-- ⑥ 자소서 문항 (input_coverletteritem)
--    필드: id(UUID), cover_letter_id, question, answer_text,
--          max_length, order_index, created_at, updated_at
INSERT INTO input_coverletteritem (
    id,
    cover_letter_id,
    question,
    answer_text,
    max_length,
    order_index,
    created_at,
    updated_at
) VALUES
(
    @cl_item1_uuid,
    @cl_uuid,
    '지원 동기와 입사 후 이루고 싶은 목표를 말씀해주세요.',
    '배달 플랫폼에서 주문·정산 API를 개발하며 대용량 트래픽 환경의 성능 최적화에 깊은 관심을 갖게 되었습니다. 테크스타트업이 추구하는 이벤트 기반 아키텍처와 Kubernetes 기반 MSA 전환 로드맵에 공감하며 이 환경에서 실무 역량을 넓히고 싶습니다. 입사 후에는 기존 Django 서비스의 병목을 분석하고 Redis 캐싱 전략을 고도화하는 데 기여하겠습니다.',
    1000,
    1,
    NOW(),
    NOW()
),
(
    @cl_item2_uuid,
    @cl_uuid,
    '본인이 주도적으로 문제를 발견하고 개선한 경험을 구체적으로 설명해주세요.',
    '배달 플랫폼 재직 중 배달 상태 조회 API 응답 시간이 피크 타임에 평균 800ms까지 치솟는 문제를 발견했습니다. 팀에서 인지하지 못하던 상황에서 제가 먼저 쿼리 실행 계획을 분석해 N+1 문제와 불필요한 JOIN을 확인했습니다. Redis TTL 기반 캐싱 레이어를 도입하고 쿼리를 리팩토링한 결과 응답 시간이 평균 120ms로 85% 감소했고 서버 부하도 30% 줄었습니다.',
    1000,
    2,
    NOW(),
    NOW()
);

-- ============================================================
--  생성된 ID 확인 (분석 API 호출 시 사용)
-- ============================================================
SELECT
    @user_id           AS user_id,
    @jd_uuid           AS jd_id,
    @resume_uuid       AS resume_id,
    @cl_uuid           AS cover_letter_id;
