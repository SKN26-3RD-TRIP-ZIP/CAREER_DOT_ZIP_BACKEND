-- =============================================================================
-- LLM 평가 테스트용 시드 데이터
-- 대상 DB: MySQL (career_dot_zip)
-- 실행 순서: 테이블 의존성 순서대로 작성됨
--   1. accounts_user
--   2. input_userprofile
--   3. input_jobdescription        (jd_samples.json 3건)
--   4. input_resumemaster          (resume_samples.json 2건)
--   5. input_resumecareer
--   6. input_resumeskill
--   7. input_resumeeducation
--   8. input_coverletter
--   9. input_coverletteritem
--  10. question_bank_items         (RAG MySQL 폴백용)
-- =============================================================================

-- 중복 실행 방지: 같은 ID가 이미 있으면 건너뜀
-- (INSERT IGNORE 또는 ON DUPLICATE KEY UPDATE 사용)

-- -----------------------------------------------------------------------------
-- 1. 테스트 유저 — id=8 기존 계정 사용 (INSERT 생략)
-- -----------------------------------------------------------------------------

-- -----------------------------------------------------------------------------
-- 2. 유저 프로필
-- -----------------------------------------------------------------------------
INSERT INTO input_userprofile
    (id, user_id, career_type, major_type, desired_job, career_year, github_url, created_at, updated_at)
VALUES
    (REPLACE(UUID(), '-', ''),
     8,
     '경력', '전공', '백엔드 개발자', 2, NULL,
     NOW(), NOW())
ON DUPLICATE KEY UPDATE user_id = VALUES(user_id);

-- -----------------------------------------------------------------------------
-- 3. JobDescription — jd_samples.json 3건과 매핑
--    UUID를 고정값으로 지정해 eval/run_eval.py에서 참조 가능
-- -----------------------------------------------------------------------------
INSERT INTO input_jobdescription
    (id, user_id, company_name, position, original_text,
     input_method, analysis_status, created_at, updated_at)
VALUES
    ('00000000000000000000000000000001',
     8,
     '테크스타트업A', '백엔드 개발자',
     '저희는 Python/Django 기반의 백엔드 개발자를 모집합니다.\n\n[주요 업무]\n- RESTful API 설계 및 개발\n- 데이터베이스 설계 및 최적화\n- 클라우드 인프라(AWS) 운영 및 개선\n\n[자격 요건]\n- Python, Django 실무 경험 2년 이상\n- PostgreSQL 또는 MySQL 사용 경험\n- Git 기반 협업 경험\n\n[우대 사항]\n- Docker, Kubernetes 사용 경험\n- Redis 캐싱 경험\n- 스타트업 경험자\n\n[인재상]\n- 주도적으로 문제를 해결하는 분\n- 빠른 피드백 루프를 즐기는 분\n- 동료와 적극적으로 소통하며 협업하는 분',
     'TEXT', 'COMPLETED', NOW(), NOW()),

    ('00000000000000000000000000000002',
     8,
     '이커머스B', '프론트엔드 개발자',
     'React 기반 프론트엔드 개발자를 채용합니다.\n\n[주요 업무]\n- React/TypeScript 기반 웹 서비스 개발\n- 사용자 경험 개선 및 성능 최적화\n- 디자이너 및 백엔드 개발자와의 협업\n\n[자격 요건]\n- React 실무 경험 1년 이상\n- JavaScript/TypeScript 능숙자\n- HTML/CSS 기본기 보유\n\n[우대 사항]\n- Next.js 사용 경험\n- 성능 최적화(Lighthouse 90점 이상) 경험\n- 디자인 시스템 구축 경험\n\n[인재상]\n- 사용자 관점에서 생각하는 분\n- 꼼꼼하고 완성도를 중시하는 분\n- 지속적으로 학습하고 성장하는 분',
     'TEXT', 'COMPLETED', NOW(), NOW()),

    ('00000000000000000000000000000003',
     8,
     '핀테크C', '데이터 엔지니어',
     '데이터 파이프라인 구축 및 운영을 담당할 데이터 엔지니어를 모집합니다.\n\n[주요 업무]\n- Airflow 기반 ETL 파이프라인 설계 및 운영\n- Spark/Hadoop을 이용한 대용량 데이터 처리\n- 데이터 품질 모니터링 및 이상 탐지\n\n[자격 요건]\n- Python 또는 Scala 실무 경험 2년 이상\n- SQL 고급 쿼리 작성 능력\n- Airflow 또는 유사 워크플로우 툴 경험\n\n[우대 사항]\n- Apache Spark 최적화 경험\n- AWS Glue, Redshift 경험\n- 금융 데이터 처리 경험\n\n[인재상]\n- 데이터 품질에 집착하는 분\n- 장애 상황에서 침착하게 대응하는 분\n- 비즈니스 맥락을 이해하고 데이터를 해석하는 분',
     'TEXT', 'COMPLETED', NOW(), NOW())
ON DUPLICATE KEY UPDATE company_name = VALUES(company_name);

-- -----------------------------------------------------------------------------
-- 4. ResumeMaster — resume_samples.json 2건과 매핑
-- -----------------------------------------------------------------------------
INSERT INTO input_resumemaster
    (id, user_id, name, phone, email,
     original_text, is_active, created_at, updated_at)
VALUES
    ('00000000000000000001000000000001',
     8, '김개발', '010-0000-0001', 'kimdev@eval.zip',
     '이름: 김개발\n\n[경력]\n- (주)웹서비스 백엔드 개발자 (2022.03 ~ 2024.02, 2년)\n  - Django REST Framework 기반 API 30개 설계 및 개발\n  - PostgreSQL 쿼리 최적화로 응답속도 40% 개선\n  - AWS EC2/S3/RDS 운영 및 장애 대응\n\n[기술 스택]\nPython, Django, PostgreSQL, Redis, AWS(EC2/S3/RDS), Docker, Git\n\n[프로젝트]\n- 중고거래 플랫폼 백엔드 개발 (2021.09 ~ 2022.02)\n  - 역할: 백엔드 리드 (3인 팀)\n  - 기술: Python, Django, MySQL, Redis\n  - 성과: 일 거래량 1,000건 처리, 응답시간 200ms 이하 달성',
     1, NOW(), NOW()),

    ('00000000000000000001000000000002',
     8, '이프론트', '010-0000-0002', 'lefront@eval.zip',
     '이름: 이프론트\n\n[경력]\n- (주)쇼핑몰 프론트엔드 개발자 (2023.01 ~ 현재, 1.5년)\n  - React/TypeScript 기반 상품 상세 페이지 리뉴얼\n  - Lighthouse 성능 점수 62점 → 91점 개선\n  - 디자인 시스템 컴포넌트 40개 구축\n\n[기술 스택]\nReact, TypeScript, Next.js, Tailwind CSS, Git, Figma\n\n[프로젝트]\n- 개인 포트폴리오 사이트 (2022.11 ~ 2022.12)\n  - 역할: 단독 개발\n  - 기술: Next.js, TypeScript, Vercel\n  - 성과: Lighthouse 성능 95점, SEO 100점 달성',
     1, NOW(), NOW())
ON DUPLICATE KEY UPDATE name = VALUES(name);

-- -----------------------------------------------------------------------------
-- 5. ResumeCareer
-- -----------------------------------------------------------------------------
INSERT INTO input_resumecareer
    (id, resume_id, company_name, position,
     start_date, end_date, is_current, description, created_at, updated_at)
VALUES
    (REPLACE(UUID(), '-', ''),
     '00000000000000000001000000000001',
     '(주)웹서비스', '백엔드 개발자',
     '2022-03', '2024-02', 0,
     'Django REST Framework 기반 API 30개 설계 및 개발\nPostgreSQL 쿼리 최적화로 응답속도 40% 개선\nAWS EC2/S3/RDS 운영 및 장애 대응',
     NOW(), NOW()),

    (REPLACE(UUID(), '-', ''),
     '00000000000000000001000000000002',
     '(주)쇼핑몰', '프론트엔드 개발자',
     '2023-01', NULL, 1,
     'React/TypeScript 기반 상품 상세 페이지 리뉴얼\nLighthouse 성능 점수 62점 → 91점 개선\n디자인 시스템 컴포넌트 40개 구축',
     NOW(), NOW());

-- -----------------------------------------------------------------------------
-- 6. ResumeSkill
-- -----------------------------------------------------------------------------
INSERT INTO input_resumeskill (id, resume_id, name, created_at)
VALUES
    -- 김개발
    (REPLACE(UUID(), '-', ''), '00000000000000000001000000000001', 'Python',     NOW()),
    (REPLACE(UUID(), '-', ''), '00000000000000000001000000000001', 'Django',     NOW()),
    (REPLACE(UUID(), '-', ''), '00000000000000000001000000000001', 'PostgreSQL', NOW()),
    (REPLACE(UUID(), '-', ''), '00000000000000000001000000000001', 'Redis',      NOW()),
    (REPLACE(UUID(), '-', ''), '00000000000000000001000000000001', 'AWS',        NOW()),
    (REPLACE(UUID(), '-', ''), '00000000000000000001000000000001', 'Docker',     NOW()),
    (REPLACE(UUID(), '-', ''), '00000000000000000001000000000001', 'Git',        NOW()),
    -- 이프론트
    (REPLACE(UUID(), '-', ''), '00000000000000000001000000000002', 'React',         NOW()),
    (REPLACE(UUID(), '-', ''), '00000000000000000001000000000002', 'TypeScript',    NOW()),
    (REPLACE(UUID(), '-', ''), '00000000000000000001000000000002', 'Next.js',       NOW()),
    (REPLACE(UUID(), '-', ''), '00000000000000000001000000000002', 'Tailwind CSS',  NOW()),
    (REPLACE(UUID(), '-', ''), '00000000000000000001000000000002', 'Git',           NOW()),
    (REPLACE(UUID(), '-', ''), '00000000000000000001000000000002', 'Figma',         NOW());

-- -----------------------------------------------------------------------------
-- 7. ResumeEducation
-- -----------------------------------------------------------------------------
INSERT INTO input_resumeeducation
    (id, resume_id, school_name, major, degree, start_date, end_date, status, created_at, updated_at)
VALUES
    (REPLACE(UUID(), '-', ''),
     '00000000000000000001000000000001',
     '한국대학교', '컴퓨터공학과', 'bachelor',
     '2018-03', '2022-02', 'graduated', NOW(), NOW()),

    (REPLACE(UUID(), '-', ''),
     '00000000000000000001000000000002',
     '서울대학교', '소프트웨어학과', 'bachelor',
     '2019-03', NULL, 'enrolled', NOW(), NOW());

-- -----------------------------------------------------------------------------
-- 8. CoverLetter (자기소개서 묶음)
-- -----------------------------------------------------------------------------
INSERT INTO input_coverletter
    (id, user_id, jd_id, title, company_name, is_active, created_at, updated_at)
VALUES
    ('00000000000000000002000000000001',
     8,
     '00000000000000000000000000000001',
     '테크스타트업A 백엔드 개발자 지원',
     '테크스타트업A', 1, NOW(), NOW()),

    ('00000000000000000002000000000002',
     8,
     '00000000000000000000000000000002',
     '이커머스B 프론트엔드 개발자 지원',
     '이커머스B', 1, NOW(), NOW())
ON DUPLICATE KEY UPDATE title = VALUES(title);

-- -----------------------------------------------------------------------------
-- 9. CoverLetterItem (자소서 항목)
-- -----------------------------------------------------------------------------
INSERT INTO input_coverletteritem
    (id, cover_letter_id, question, answer_text, max_length, order_index, created_at, updated_at)
VALUES
    (REPLACE(UUID(), '-', ''),
     '00000000000000000002000000000001',
     '지원 동기 및 입사 후 포부를 서술하세요.',
     '저는 문제를 데이터로 접근하는 개발자입니다. 이전 직장에서 API 응답 속도 문제가 발생했을 때, 단순히 서버 증설을 제안하는 대신 쿼리 실행 계획을 분석해 인덱스 최적화로 해결했습니다. 팀원들과 의견이 다를 때는 항상 실험과 수치로 설득하는 편이며, 이런 방식이 팀 전체의 기술적 의사결정 수준을 높였다고 생각합니다.',
     1000, 1, NOW(), NOW()),

    (REPLACE(UUID(), '-', ''),
     '00000000000000000002000000000002',
     '본인의 강점과 개발 철학을 서술하세요.',
     '사용자가 불편함을 느끼기 전에 먼저 발견하는 개발자가 되고 싶습니다. 쇼핑몰에서 모바일 사용자의 이탈률이 높다는 데이터를 보고, 스스로 원인을 분석해 이미지 최적화와 레이아웃 시프트 제거 작업을 제안했습니다. 결과적으로 모바일 전환율이 18% 향상되었습니다. 꼼꼼함과 완성도에 대한 집착이 저의 강점입니다.',
     1000, 1, NOW(), NOW());

-- -----------------------------------------------------------------------------
-- 10. question_bank_items — RAG MySQL 폴백용
--     job_category='ICT', is_active=1 조건에 걸려야 검색됨
--     question_hash = SHA2(question_text, 256)과 일치해야 unique 제약 통과
--     (여기서는 간략한 고정 해시값 사용 — 실제 데이터가 없는 경우 폴백 동작 검증용)
-- -----------------------------------------------------------------------------
INSERT INTO question_bank_items
    (id, job_category, question_text, answer_example, question_type,
     difficulty, keywords, source, source_file, source_ref,
     question_hash, raw_metadata, is_active, is_embedded, created_at, updated_at)
VALUES
    -- 백엔드 기술 질문
    ('10000000000000000000000000000001',
     'ICT',
     'Django REST Framework에서 인증 방식(Session vs JWT)의 차이와 각각 적합한 사용 사례를 설명해주세요.',
     'Session 인증은 서버에 상태를 저장하므로 단일 서버 환경에 적합하고, JWT는 무상태(Stateless)로 마이크로서비스나 모바일 환경에 유리합니다.',
     'technical', 'medium',
     '["Django", "DRF", "JWT", "Session", "인증"]',
     'eval_seed', 'seed_eval_data.sql', 'manual',
     SHA2('Django REST Framework에서 인증 방식(Session vs JWT)의 차이와 각각 적합한 사용 사례를 설명해주세요.', 256),
     '{}', 1, 0, NOW(), NOW()),

    ('10000000000000000000000000000002',
     'ICT',
     'PostgreSQL에서 N+1 문제가 발생하는 상황과 해결 방법을 설명해주세요.',
     'N+1 문제는 ORM에서 연관 객체를 개별 쿼리로 조회할 때 발생합니다. select_related(JOIN)나 prefetch_related(서브쿼리 IN)로 해결합니다.',
     'technical', 'medium',
     '["PostgreSQL", "ORM", "N+1", "쿼리 최적화", "Django"]',
     'eval_seed', 'seed_eval_data.sql', 'manual',
     SHA2('PostgreSQL에서 N+1 문제가 발생하는 상황과 해결 방법을 설명해주세요.', 256),
     '{}', 1, 0, NOW(), NOW()),

    ('10000000000000000000000000000003',
     'ICT',
     'Redis를 캐시 레이어로 활용할 때 Cache-Aside 패턴과 Write-Through 패턴의 차이를 설명해주세요.',
     'Cache-Aside는 읽기 요청 시 캐시 미스가 나면 DB에서 읽어 캐시에 저장합니다. Write-Through는 쓰기 시 캐시와 DB를 동시에 갱신해 일관성을 보장합니다.',
     'technical', 'hard',
     '["Redis", "캐싱", "Cache-Aside", "Write-Through", "인프라"]',
     'eval_seed', 'seed_eval_data.sql', 'manual',
     SHA2('Redis를 캐시 레이어로 활용할 때 Cache-Aside 패턴과 Write-Through 패턴의 차이를 설명해주세요.', 256),
     '{}', 1, 0, NOW(), NOW()),

    ('10000000000000000000000000000004',
     'ICT',
     'AWS에서 배포 시 EC2, ECS, Lambda 중 어떤 상황에 어떤 서비스를 선택하시겠습니까?',
     'EC2는 긴 실행 시간과 상태 유지가 필요한 서비스, ECS는 컨테이너 기반 마이크로서비스, Lambda는 이벤트 기반 단기 작업에 적합합니다.',
     'technical', 'medium',
     '["AWS", "EC2", "Lambda", "ECS", "클라우드", "인프라"]',
     'eval_seed', 'seed_eval_data.sql', 'manual',
     SHA2('AWS에서 배포 시 EC2, ECS, Lambda 중 어떤 상황에 어떤 서비스를 선택하시겠습니까?', 256),
     '{}', 1, 0, NOW(), NOW()),

    -- 프론트엔드 기술 질문
    ('10000000000000000000000000000005',
     'ICT',
     'React에서 상태 관리 라이브러리(Redux, Zustand, Recoil)를 선택하는 기준을 설명해주세요.',
     '프로젝트 규모와 팀 숙련도를 기준으로 선택합니다. Redux는 대형 프로젝트, Zustand는 경량 관리, Recoil은 파생 상태가 많을 때 유리합니다.',
     'technical', 'medium',
     '["React", "Redux", "Zustand", "상태 관리", "TypeScript"]',
     'eval_seed', 'seed_eval_data.sql', 'manual',
     SHA2('React에서 상태 관리 라이브러리(Redux, Zustand, Recoil)를 선택하는 기준을 설명해주세요.', 256),
     '{}', 1, 0, NOW(), NOW()),

    ('10000000000000000000000000000006',
     'ICT',
     'Next.js의 SSR, SSG, ISR의 차이를 설명하고 각각 적합한 페이지 유형을 예를 들어 설명해주세요.',
     'SSR은 요청마다 서버 렌더링(실시간 데이터), SSG는 빌드 시 정적 생성(변경 없는 콘텐츠), ISR은 주기적 재생성(자주 바뀌지 않는 콘텐츠)에 적합합니다.',
     'technical', 'medium',
     '["Next.js", "SSR", "SSG", "ISR", "React", "TypeScript"]',
     'eval_seed', 'seed_eval_data.sql', 'manual',
     SHA2('Next.js의 SSR, SSG, ISR의 차이를 설명하고 각각 적합한 페이지 유형을 예를 들어 설명해주세요.', 256),
     '{}', 1, 0, NOW(), NOW()),

    -- 데이터 엔지니어링 질문
    ('10000000000000000000000000000007',
     'ICT',
     'Apache Airflow에서 DAG 스케줄링 시 catchup 옵션이 미치는 영향을 설명해주세요.',
     'catchup=True이면 과거 누락된 실행 구간을 모두 소급 실행합니다. 파이프라인 재시작 시 의도치 않은 대량 실행이 발생할 수 있어 운영 환경에서는 False로 설정하는 것이 안전합니다.',
     'technical', 'medium',
     '["Airflow", "ETL", "스케줄링", "DAG", "Python"]',
     'eval_seed', 'seed_eval_data.sql', 'manual',
     SHA2('Apache Airflow에서 DAG 스케줄링 시 catchup 옵션이 미치는 영향을 설명해주세요.', 256),
     '{}', 1, 0, NOW(), NOW()),

    ('10000000000000000000000000000008',
     'ICT',
     'Apache Spark에서 Narrow Transformation과 Wide Transformation의 차이와 셔플이 성능에 미치는 영향을 설명해주세요.',
     'Narrow는 파티션 내에서만 데이터를 처리해 셔플이 없고, Wide는 파티션 간 데이터 이동(셔플)이 발생합니다. 셔플은 네트워크 I/O와 디스크 쓰기를 유발해 가장 큰 성능 병목입니다.',
     'technical', 'hard',
     '["Spark", "Hadoop", "분산처리", "셔플", "데이터파이프라인"]',
     'eval_seed', 'seed_eval_data.sql', 'manual',
     SHA2('Apache Spark에서 Narrow Transformation과 Wide Transformation의 차이와 셔플이 성능에 미치는 영향을 설명해주세요.', 256),
     '{}', 1, 0, NOW(), NOW()),

    -- 공통 인성 질문
    ('10000000000000000000000000000009',
     'ICT',
     '팀 내에서 기술적 의견 충돌이 발생했을 때 어떻게 해결한 경험이 있나요?',
     '의견 충돌 시 주관적 판단보다 데이터와 실험을 기반으로 설득하는 방식을 선호합니다. A/B 테스트나 벤치마크로 객관적 근거를 마련해 팀 합의를 이끌어낸 사례를 구체적으로 답변하면 좋습니다.',
     'personality', 'easy',
     '["협업", "커뮤니케이션", "문제해결", "팀워크"]',
     'eval_seed', 'seed_eval_data.sql', 'manual',
     SHA2('팀 내에서 기술적 의견 충돌이 발생했을 때 어떻게 해결한 경험이 있나요?', 256),
     '{}', 1, 0, NOW(), NOW()),

    ('10000000000000000000000000000010',
     'ICT',
     '본인이 주도적으로 개선을 제안하고 실행에 옮긴 경험을 STAR 형식으로 설명해주세요.',
     'Situation: 문제 상황 정의 → Task: 본인의 역할과 목표 → Action: 구체적으로 취한 행동 → Result: 수치화된 결과. 본인의 주도성과 문제 해결 과정을 명확히 드러내는 것이 중요합니다.',
     'personality', 'medium',
     '["주도성", "문제해결", "성과", "리더십", "STAR"]',
     'eval_seed', 'seed_eval_data.sql', 'manual',
     SHA2('본인이 주도적으로 개선을 제안하고 실행에 옮긴 경험을 STAR 형식으로 설명해주세요.', 256),
     '{}', 1, 0, NOW(), NOW())

ON DUPLICATE KEY UPDATE question_text = VALUES(question_text);

-- =============================================================================
-- 삽입 확인 쿼리 (실행 후 검증용)
-- =============================================================================
-- SELECT '=== accounts_user ===' AS check_target;
-- SELECT id, email, name FROM accounts_user WHERE id = 8;
--
-- SELECT '=== input_jobdescription ===' AS check_target;
-- SELECT id, company_name, position FROM input_jobdescription WHERE user_id = 8;
--
-- SELECT '=== input_resumemaster ===' AS check_target;
-- SELECT id, name FROM input_resumemaster WHERE user_id = 8;
--
-- SELECT '=== question_bank_items ===' AS check_target;
-- SELECT id, question_type, LEFT(question_text, 40) AS q FROM question_bank_items WHERE source = 'eval_seed';
