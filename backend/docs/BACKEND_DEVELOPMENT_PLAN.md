# 사회복지 상담 AX Tool — 백엔드 개발 계획

- 작성일: 2026-09-04
- 상태: 구현 전 계획안
- 구현 위치: `backend/`
- 기준: [기능 명세](../../docs/SPEC.md), [API 명세](../../docs/API_SPEC.md)
- 확정 결정: STT와 LLM 모두 OpenAI API 사용. 구체적인 모델 ID는 P0에서 검증 후 확정

## 1. 목표와 문서 적용 기준

사회복지사가 상담 음성을 업로드한 뒤 전사문과 상담일지를 각각 검토·확정하고, 확정 기록을 바탕으로 위험신호·추천 Action·사례회의 리포트를 얻는 MVP 백엔드를 개발한다.

현재 `backend/`와 `frontend/`에는 구현 코드가 없다. 기능 명세에 지정된 **FastAPI + Railway PostgreSQL**을 유지하며, 이 문서는 구현 순서·내부 설계·검증 기준을 추가한다. 기능 명세의 “백엔드 전용 레포”라는 표현은 현재 폴더 구조와 사용자의 지시에 맞춰 **백엔드 구현을 `backend/`에 한정한다**는 의미로 적용한다.

외부 API 경로·필드·상태 코드는 루트 API 명세를 기준으로 한다. 아래에서 “제안”으로 표시한 내부 설계는 아직 구현되거나 사용자 승인을 받은 기술 결정이 아니다. 계약 변경이 필요하면 먼저 해당 명세와 본 문서를 함께 갱신한다.

### MVP 범위

- 내담자 등록, 목록·검색·상세 및 상담 이력 조회
- 녹음 업로드, 비동기 STT, 전사문 수정·확정
- 상담일지 초안 생성, 수정·확정
- 확정 상담 기반 상태변화·위험신호·미해결 이슈·추천 Action 생성
- Action 조회 및 상태 변경
- 여러 확정 상담을 종합한 동기 사례회의 리포트 생성

### 제외 범위

로그인·회원가입·기관별 권한, 실제 전화 연결·녹음·실시간 STT, 외부 복지시스템·메시지 발송, RAG·Vector DB·AI Agent, 자체 위험 예측, 의료·법률 판단, PDF/HWP 출력, 복잡한 통계, 수동 재실행·재분석 API는 구현하지 않는다. Risk 해결 처리 API와 리포트 저장·조회 API도 추가하지 않는다.

## 2. 반드시 지킬 처리 원칙

1. 업로드는 STT까지만 실행한다. 전사문 확정 전에는 상담일지를 만들지 않는다.
2. 전사문·상담일지 PATCH는 저장만 수행한다. AI 작업을 실행하지 않는다.
3. 전사문 확정은 상담일지 초안만 생성한다. 상담일지 확정 이후에만 후속 분석한다.
4. 확정 이후 원문을 잠근다. 상담자가 수정·삭제한 사실을 예전 초안에서 복원하지 않는다.
5. 상태 확인과 저장·확정은 원자적으로 처리한다. 동시 중복 확정은 하나만 성공하고 나머지는 `409`다.
6. 작업 예약 실패 시 `503`을 반환하고, 확정 상태·확정 시각도 함께 롤백한다.
7. 분석 결과·Risk·Action 저장이 모두 성공해야 `DONE`이다. 부분 결과를 노출하지 않는다.
8. 미생성 결과와 분석 완료 후 빈 결과를 구별한다. 실패해도 이미 저장된 전사문·상담일지는 조회할 수 있다.
9. 상담일과 업로드일을 구분한다. 과거 기록 업로드가 현재 상태나 Action 기한을 잘못 바꾸지 않게 한다.
10. AI 결과는 보조 정보다. 근거 없는 사실·확정 진단을 생성하지 않으며 불명확하면 `UNKNOWN` 또는 `확인 필요`로 처리한다.

## 3. 기술 구성과 책임 분리

### 3.1 기술 선택

| 영역 | 계획 | 상태·이유 |
| --- | --- | --- |
| API | Python + FastAPI + Uvicorn | FastAPI는 기능 명세 기준. Python 및 패키지 버전은 초기 호환성 검증 후 고정 |
| 요청·AI 출력 검증 | Pydantic, 환경 설정 모델 | 제안. API 입력과 외부 AI 응답을 별도 스키마로 검증 |
| DB | Railway PostgreSQL | 기능 명세 기준. 로컬·통합 테스트도 PostgreSQL 사용 |
| 영속성 | SQLAlchemy + Alembic | 제안. 트랜잭션과 스키마 이력을 명시적으로 관리 |
| 비동기 작업 | PostgreSQL 작업 테이블 + 앱 수명주기에서 구동하는 작업 실행기 | 제안. MVP는 단일 인스턴스·단일 Uvicorn 프로세스로 제한 |
| 외부 연동 | OpenAI API, STT/LLM 어댑터, 공식 Python SDK | OpenAI 사용은 사용자 확정. 구체 모델 ID는 미정. 테스트에서는 동일 인터페이스의 fake 사용 |
| 음성 | 전용 임시 디렉터리, 로컬 오디오 검사 도구 | 영구 보관하지 않음. 검사 도구·코덱 지원은 초기 검증에서 확정 |
| 테스트·품질 | pytest, HTTPX, Ruff, 타입 검사 | 제안. 구체 버전·타입 검사 도구는 초기 설정에서 고정 |
| 배포 | `backend/` 기준 Docker 이미지, Railway | 기능 명세의 배포 방향 유지. 실제 배포는 후속 구현 단계 |

DB 비동기 세션을 사용하는 방향을 제안한다. 요청과 작업마다 세션을 따로 만들고 공유하지 않는다. 동기 SDK나 오디오 검사가 필요하면 제한된 스레드/서브프로세스로 분리해 API 이벤트 루프를 막지 않는다.

### 3.2 예정 폴더 구조

아래 경로는 향후 만들 산출물이며 현재 구현되어 있다는 뜻이 아니다.

```text
backend/
  docs/BACKEND_DEVELOPMENT_PLAN.md
  pyproject.toml
  .env.example
  Dockerfile
  compose.yaml
  alembic.ini
  migrations/versions/
  app/
    main.py
    api/                  # clients, consultations, actions, case_reports, health
    schemas/              # 요청·응답 모델 및 AI 출력 모델
    services/             # 검토·확정, 상태 전이, 분석, 리포트 업무 규칙
    repositories/         # 조회·저장, 집계, 잠금 및 작업 예약 쿼리
    models/               # ORM 모델·열거형
    db/                   # 엔진·세션 설정
    integrations/         # stt, llm, audio_storage, audio_validator
    jobs/                 # runner, handlers, recovery, cleanup
    prompts/              # counseling_note, follow_up_analysis, case_report
    core/                 # config, errors, logging, 시간 처리
  tests/
    unit/
    integration/
    contract/
    e2e/
    fixtures/             # 가명·합성 상담과 AI 응답
```

라우터는 검증된 요청을 서비스에 전달하고 응답을 직렬화한다. 서비스가 트랜잭션 경계와 상태 전이를 관리하고, 저장소는 SQL을 담당한다. OpenAI STT·LLM의 예외와 응답은 각각 연동 어댑터에서 내부 형식으로 변환한다. 다중 공급자 라우팅은 MVP에서 구현하지 않는다. 프롬프트에 DB 조회나 상태 변경 책임을 넣지 않는다.

### 3.3 주요 설계 선택과 대안

- **모듈형 단일 애플리케이션:** MVP 운영 비용과 개발 범위를 줄인다. 단점은 작업 부하와 API가 자원을 공유한다는 점이다. 독립 worker·마이크로서비스는 실제 부하 및 운영 필요가 확인된 뒤 검토한다.
- **DB 작업 예약:** 상담 상태와 작업을 한 트랜잭션에 기록한다. 별도 Redis/Celery 없이 예약 유실을 탐지할 수 있지만 작업 선점·복구 로직을 구현해야 한다. 메모리에만 예약하는 방식은 재시작 후 대기 작업을 식별하기 어려우므로 핵심 처리의 유일한 예약 수단으로 사용하지 않는다. FastAPI의 응답 후 작업 실행 방식은 [공식 Background Tasks 문서](https://fastapi.tiangolo.com/tutorial/background-tasks/)를 참고한다.
- **임시 오디오:** 명세대로 STT 이후 삭제한다. 대신 재배포 시 파일 유실을 허용하고 해당 STT를 명시적으로 실패 처리한다. 파일 복구까지 보장하려면 임시 객체 저장소와 수명주기 정책에 대한 별도 설계 결정이 필요하다.
- **관계형 데이터 + 제한적인 JSONB:** 변경 가능한 Action·Risk는 관계형 테이블, 구조화 상태·변화는 JSONB로 관리한다. 응답 전체를 JSON으로 저장하면 Action 변경이 조회에 반영되지 않으므로 피한다.

## 4. 데이터 모델·조회 설계

기능 명세의 다섯 도메인 모델을 유지하고, 작업 실행에 필요한 내부 모델을 추가한다.

| 테이블 | 주요 데이터 | 제약·용도 |
| --- | --- | --- |
| `clients` | 이름, 출생연도, 성별, 메모, 생성 시각 | 양의 정수 ID. 동명이인 허용 |
| `consultations` | 내담자 FK, 실제 상담 시각, 전사문, 전사문 확정 시각, 상태, 실패 단계·코드, 생성 시각 | 내담자 존재 검증. 상태는 명세의 8개 값 |
| `analyses` | 상담 FK, `counseling_note` JSONB, 상담일지 확정 시각, nullable `analysis_json`, 생성 시각, 분석 완료 시각 | `consultation_id UNIQUE`. 초안이 있어도 최종 분석은 없을 수 있음 |
| `risk_flags` | 상담 FK, 유형·심각도·설명·근거, resolved, 생성 시각 | 생성 시 resolved=false. 전사 근거가 없으면 evidence=null |
| `action_items` | 내담자·상담 FK, 유형·제목·설명·우선순위·사유·기한·상태, 생성 시각 | 생성 시 TODO. 상담과 내담자의 관계 불일치 방지 |
| `processing_jobs` | 상담 FK, 단계, 내부 상태, 시도 횟수, 다음 실행 시각, 실행 소유자·토큰, lease 만료, 임시 파일 식별자, 생성·갱신 시각 | 내부 구현용. `UNIQUE(consultation_id, stage)`로 단계별 예약 중복 방지 |

### 저장 일관성

- `counseling_note`는 `summary`, `main_contents`, `client_status`의 단일 원본이다. 확정 시각도 `analyses` 한 곳에 두고 Consultation 응답에서 매핑한다.
- 초안 생성 시 `analysis_json`은 SQL NULL이다. 후속 분석 완료 시에만 요약·상태·비교 상담 ID·변화·미해결 이슈를 기록한다.
- 최종 요약과 상태는 상담자가 확정한 상담일지를 기준으로 만들며, 원래 초안의 상태를 재사용하지 않는다.
- Risk·Action은 테이블에서 조회해 최종 응답을 구성한다. `recommended_actions`에 저장 시점의 상태 복사본을 사용하지 않는다.
- 확정 상담일지의 `created_at`과 최종 분석 응답의 `created_at`은 각각 초안 생성 시각과 분석 완료 시각에 매핑한다.
- 시간은 timezone-aware UTC로 저장·응답한다. `due_date`만 실제 상담 시각을 `Asia/Seoul`로 변환한 날짜에 `due_in_days`를 더한다. 근거 없는 기한은 null이다.
- 내담자·상담 삭제 API 및 자동 연쇄 삭제는 MVP에서 제공하지 않는다.

### 조회·인덱스

- 상담 이력 및 비교: `(client_id, consulted_at DESC, id DESC)`, 필요 시 DONE 부분 인덱스.
- Action 목록: `(client_id, status, due_date, id)`. 기한 null은 마지막에 둔다.
- 중요 Risk: 미해결 HIGH 조건과 상담 FK를 활용하는 인덱스.
- 작업 선점: 내부 상태·다음 실행 시각 및 lease 만료 조회 인덱스.
- 내담자 목록 집계는 집계 서브쿼리 등으로 가져와 내담자별 반복 쿼리를 피한다. `total`에도 동일 검색 필터를 적용한다.
- 이름 부분 일치 검색은 파라미터 바인딩을 사용하고 `%`, `_`를 일반 검색 문자로 처리한다. 데이터가 작을 때 별도 검색 엔진은 도입하지 않는다.
- `last_consulted_at`은 FAILED 제외 전체 상담 중 최댓값, `current_status`는 가장 최근 DONE 상담 기준이다. 최근 상담 5건은 실패·진행 중도 포함한다.
- 이전 비교 대상은 같은 내담자, DONE, 현재 상담보다 엄격히 이른 `consulted_at`, 최신순 최대 5건이다. 동률 정렬은 ID로 고정한다.
- 이전 상담이 나중에 추가되더라도 기존 DONE 분석을 자동 재생성하지 않는다. 실제 사용한 비교 ID를 보존한다.

## 5. 상태 전이·비동기 작업

| 진입 상태 | 수행 | 성공 상태 | 실패 시 |
| --- | --- | --- | --- |
| 업로드 접수 전 | 파일 검증·임시 저장, 상담·STT 작업 예약 | UPLOADED, HTTP 202 | 입력 오류 또는 503. 생성·예약 롤백 및 파일 정리 |
| UPLOADED | 작업 선점·STT 시작 | TRANSCRIBING | FAILED / UPLOADED |
| TRANSCRIBING | 전사 저장 | AWAITING_TRANSCRIPT_REVIEW | FAILED / TRANSCRIBING |
| AWAITING_TRANSCRIPT_REVIEW | PATCH | 동일 상태 | 허용 상태가 아니면 409 |
| AWAITING_TRANSCRIPT_REVIEW | 전사문 확정·작업 예약 | GENERATING_NOTE, HTTP 202 | 예약 실패는 503 및 원상 복구 |
| GENERATING_NOTE | 상담일지 초안 저장 | AWAITING_NOTE_REVIEW | FAILED / GENERATING_NOTE |
| AWAITING_NOTE_REVIEW | PATCH | 동일 상태 | 허용 상태가 아니면 409 |
| AWAITING_NOTE_REVIEW | 상담일지 확정·작업 예약 | ANALYZING, HTTP 202 | 예약 실패는 503 및 원상 복구 |
| ANALYZING | 분석·Risk·Action 일괄 저장 | DONE | FAILED / ANALYZING |
| DONE 또는 FAILED | 상담 조회만 허용 | 상태 유지 | 재확정·수정은 409 |

표의 실패 단계는 API 명세의 `failure.stage`이며, 코드·사용자용 메시지도 명세에 맞춘다. Action 상태 변경은 상담 상태와 독립적이다.

### 5.1 예약과 원자적 저장

1. 업로드는 파일 검사와 임시 저장을 완료한 후 상담 및 STT 작업을 하나의 트랜잭션으로 커밋한다. 성공한 경우에만 `202`를 반환한다.
2. PATCH와 확정은 동일 상담 행 잠금 규칙을 사용한다. 확정 시 상태 확인, 확정 시각, 다음 상태, 작업 INSERT를 함께 커밋한다. 동시에 들어온 PATCH가 확정 후 내용을 바꾸지 못하게 한다.
3. 실행기는 작업을 짧은 트랜잭션에서 선점한다. 외부 AI 호출 동안 DB 트랜잭션이나 행 잠금을 유지하지 않는다.
4. 결과 저장 직전에 작업 소유 토큰과 현재 상태를 확인한다. 유효한 실행만 결과와 다음 상태, 작업 완료를 한 번에 커밋한다.
5. 결과 저장이 실패하면 전체 롤백한다. 이후 별도 트랜잭션으로 제한 재시도 또는 최종 실패를 기록한다. DB 자체가 불가능하면 복구기가 만료 작업을 처리한다.

트랜잭션 구현은 [SQLAlchemy 세션 문서](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)의 begin/commit/rollback 경계를 따른다. 작업 선점에 `FOR UPDATE SKIP LOCKED`를 사용하는 방안을 제안하며, 일반 업무 조회에는 사용하지 않는다. PostgreSQL도 이를 큐 형태 테이블의 잠금 경합 회피 용도로 설명한다. [PostgreSQL SELECT 문서](https://www.postgresql.org/docs/current/sql-select.html)

### 5.2 재시도·재시작

- 네트워크 단절·제공자 과부하·일시적 5xx는 총 시도 횟수와 총 소요 시간을 제한해 지수 백오프로 재시도한다. 값은 제공자 검증 단계에서 확정한다.
- 잘못된 인증·지원 불가 입력 등 영구 오류는 반복하지 않는다. AI 스키마 불일치는 별도 제한 횟수만 교정 시도하고 실패로 처리한다.
- 내부 재시도는 외부 `FAILED` 전환 전 같은 작업에서만 한다. 이미 FAILED인 상담을 되살리는 API는 만들지 않는다.
- 중단 감지는 lease·heartbeat로 한다. 이전 실행의 lease가 유효한 동안 새 실행이 선점하지 않는다. 만료 후 소유 토큰을 바꾸어 늦게 도착한 이전 응답의 저장을 차단한다.
- STT 작업은 파일이 있는 실행 인스턴스에 귀속시킨다. 재배포 중 새 인스턴스가 이전 인스턴스의 살아 있는 업로드 작업을 가져가지 않도록 파일 소유자와 heartbeat를 확인한다.
- 파일이 유실된 STT는 lease 만료 후 FAILED로 정리한다. 단계가 시작 전이면 UPLOADED, 시작 후면 TRANSCRIBING 실패로 기록한다. 새 업로드는 별도 상담이다.
- 전사문 이후 단계는 DB에 입력이 있으므로 만료 작업을 제한 범위에서 복구할 수 있다. 입력·비교 상담 ID는 첫 실행에 고정해 재시도 중 비교 대상이 바뀌지 않게 한다.
- 단일 프로세스 제한에도 재배포 시 구·신 프로세스가 잠시 겹칠 수 있음을 고려한다. 외부 호출의 정확히 한 번 실행은 보장하지 않으며, DB 결과 중복 방지와 호출 비용 제한을 각각 검증한다.

## 6. 업로드·AI 처리 설계

### 6.1 오디오 생명주기

- 요청 바이트를 스트리밍하며 최대 용량을 제한한다. `Content-Length`와 사용자 파일명만 신뢰하지 않는다. multipart 파싱 단계도 요청 크기·필드·파일 개수를 제한한다.
- 확장자·MIME 허용 목록과 실제 컨테이너·코덱·길이 검사를 함께 수행한다. 빈 파일·손상된 오디오는 422, 미지원 형식은 415, 크기 초과는 413이다.
- 서버 생성 임의 파일명을 사용한다. 파일은 정해진 임시 디렉터리 밖에 쓸 수 없고 HTTP로 공개하지 않는다.
- 검사 도구는 로컬 파일만 읽도록 하고 원격 URL·외부 참조·셸 해석을 막는다. 검사 시간·메모리·실행 동시성을 제한한다.
- STT가 성공하면 전사문 DB 커밋 후 삭제한다. 최종 실패·검증 실패·접수 실패에서도 삭제한다. 내부 재시도 중에만 제한 시간 동안 보관한다.
- 정상 종료의 `finally`만으로 충분하지 않다. 시작 시·주기적 정리에서 고아 파일을 처리하고, 활성 작업 파일은 보호한다. 삭제 실패는 재시도 및 운영 경고로 남긴다.
- 임시 파일을 DB·백업·이미지에 넣지 않는다. 원본 업로드 요청 객체를 백그라운드 작업에 넘기지 않고, 서버가 관리하는 파일 식별자만 전달한다.

### 6.2 AI 호출을 세 종류로 분리

| 작업 | 입력 | 검증된 출력·저장 |
| --- | --- | --- |
| 상담일지 초안 | 확정 전사문, 필요한 최소 상담 메타데이터 | summary, main_contents, 6개 client_status만 저장 |
| 후속 분석 | 최종 확정 상담일지, 근거 확인용 전사문, 이전 DONE 기록 최대 5건 | 확정본 반영 상태, 비교 ID, 변화, Risk, 이슈, Action |
| 사례회의 리포트 | 최근 DONE 기록 최대 10건, 현재 TODO Action, 미해결 Risk, 최소 내담자 정보 | 7개 리포트 항목, 사용 상담 ID, 생성 시각을 동기 반환 |

- STT와 LLM 공급자는 OpenAI로 확정한다. 구체 모델 ID는 `OPENAI_STT_MODEL`, `OPENAI_LLM_MODEL`로 분리하고 P0에서 검증 후 고정한다. 테스트 fixture는 실데이터나 실제 공급자 호출에 의존하지 않는다.
- STT는 OpenAI 파일 전사 API(`POST /v1/audio/transcriptions`)를 사용한다. 한국어 원문 전사를 수행하며 실시간 전사·번역은 범위에 넣지 않는다. 지원 형식·화자 구분·길이 제한은 선택 모델 기준으로 검증한다. [OpenAI 파일 전사 문서](https://developers.openai.com/api/docs/guides/speech-to-text)
- 상담일지·후속 분석·리포트는 OpenAI Responses API와 Structured Outputs를 사용하는 방향으로 설계한다. 이를 지원하는 모델을 선택하고 Pydantic 스키마로 결과를 검증한다. 스키마 준수와 사실 정확성은 별개이므로 인용·수정 반영 검증은 유지한다. [OpenAI Structured Outputs 문서](https://developers.openai.com/api/docs/guides/structured-outputs)
- 모든 AI 출력은 파싱·필수 키·enum·길이·배열 개수·참조 ID를 검증한다. 공급자가 반환한 DB ID는 신뢰하지 않고 서버가 생성·검증한다.
- 전사문·메모에 포함된 명령문은 자료로만 취급한다. 외부 도구 실행이나 임의 네트워크 접근을 허용하지 않는다.
- 후속 분석 프롬프트에는 원래 상담일지 초안을 넣지 않는다. 최종 확정본을 우선하고, 전사문과 충돌하거나 근거가 모호하면 확인 필요로 남긴다.
- 인용 `evidence`는 확정 전사문에 실제 있는지 검증한다. 검증되지 않는 인용은 null로 처리하며, 상담자의 추가 메모를 전사 인용으로 바꾸지 않는다.
- 비교 기록이 없으면 변화는 UNKNOWN이다. 빈 상태 배열을 정상으로 해석하지 않는다.
- 화자 구분은 STT 제공자의 실제 지원과 검증 결과에 따른다. 구분 불가 시 화자를 임의로 만들어 내지 않는다.
- API 입력 상한과 모델 컨텍스트 한도를 함께 검증한다. 전체 허용 전사문 및 이전 기록을 처리할 수 있는 모델·분할 전략을 선택하고, 내용을 조용히 잘라내지 않는다. 한도 초과는 안전한 단계 실패로 처리한다.
- 리포트의 기록 0건은 409, 1~2건은 있는 기록만 사용한다. 현재 Action·Risk도 같은 조회 스냅샷에서 확보한다. 양이 많으면 누락 없이 처리할 한도·분할 방식을 검증한다.
- 리포트는 동기 `200`, 제공자 실패는 `502`, 시간 초과는 `504`다. 다른 상담 상태를 변경하거나 별도 리포트 테이블을 만들지 않는다.

## 7. 단계별 개발 순서

각 단계는 **실패하는 테스트 작성 → 최소 구현 → 테스트 통과 → 리팩터링·검토** 순서로 진행한다. 난이도는 상대적인 추정이며 일정 약속이 아니다. 아래 경로는 `backend/` 기준이다.

| 단계 | 작업·주요 경로 | 의존성 | 난이도·주요 위험 | 완료 기준 |
| --- | --- | --- | --- | --- |
| P0. 계약·OpenAI 모델 검증 | OpenAI STT·LLM 모델 ID, 업로드 형식·제한, 비용·시간 한도 결정. `docs/`에 결정 기록 | 없음 | 중 / 음성 형식·품질·컨텍스트 제약 | 합성 한국어 음성 2건과 수정 상담일지 예제로 선택 모델 적합성 확인, 미정 항목 기록 |
| P1. 실행 기반 | `pyproject.toml`, `app/main.py`, `core/`, `db/`, `Dockerfile`, `compose.yaml`, `.env.example` | P0의 런타임 결정 | 중 / 환경 차이·설정 유출 | 로컬 API·PostgreSQL 실행, 설정 검증, 공통 오류, health, 테스트·정적 검사 실행 |
| P2. DB·상태·작업 기반 | `models/`, `migrations/versions/`, `repositories/`, `services/state_machine.py`, `jobs/` | P1 | 상 / 예약 유실·경쟁 조건 | 빈 DB 마이그레이션, 작업 선점·롤백·복구·중복 실행 테스트 통과 |
| P3. 내담자·조회 API | `api/clients.py`, `api/consultations.py`, 관련 schemas/services/repositories | P2 | 중 / 집계·정렬 오류 | 등록·검색·상세·상담 이력과 페이지네이션 계약 테스트 통과 |
| P4. 업로드·STT·전사 검토 | `integrations/audio_*`, `integrations/stt.py`, `jobs/handlers.py`, 전사 PATCH·confirm | P2, P3, P0의 STT 결정 | 상 / 오디오 검증·파일 유실·중복 확정 | 업로드→전사 검토 및 저장 성공, 확정이 초안 작업만 예약, 파일 정리·실패 경로 검증 |
| P5. 상담일지 생성·검토 | `schemas/ai_outputs.py`, `integrations/llm.py`, `prompts/counseling_note.*`, 관련 서비스·API | P4, P0의 LLM 결정 | 상 / 스키마 오류·수정 손실 | 확정 전사 기반 초안 생성, PATCH 전체 교체 규칙, 별도 확정, 이후 수정 차단 |
| P6. 후속 분석·Action | `prompts/follow_up_analysis.*`, `services/analysis.py`, `api/actions.py` | P5 | 상 / 확정본 무시·부분 저장 | 비교 ID·UNKNOWN·인용 검증, 결과 원자 저장, Action 변경이 모든 조회에 반영 |
| P7. 사례회의 리포트 | `api/case_reports.py`, `services/case_reports.py`, `prompts/case_report.*` | P6 | 중 / 동기 시간 초과·잘못된 근거 | 0·1·2·10건 경계, 7개 항목, 현재 TODO·Risk 반영, 502·504 검증 |
| P8. 통합·배포 준비 | `tests/e2e/`, `tests/fixtures/`, CI 설정, `docs/` 운영 안내 | P1~P7 | 상 / 외부 장애·배포 재시작 | 두 상담 데모, 회귀·재시작·파일 삭제 검증, 환경·복구·롤백 절차 완성 |

핵심 경로는 P1→P2→P3→P4→P5→P6이다. OpenAI 모델 검증 완료 전에도 fake 어댑터로 계약 테스트를 만들 수 있지만, 실제 음성·LLM 연동 검증을 완료 조건에서 생략하지 않는다. 일정이 부족해도 검토 단계·입력 검증·원자성·파일 정리를 제거하지 않는다.

### API 누락 방지 매핑

| 구현 단계 | API |
| --- | --- |
| P3 | `POST /clients`, `GET /clients`, `GET /clients/{client_id}`, `GET /clients/{client_id}/consultations`, `GET /consultations/{consultation_id}` |
| P4 | `POST /clients/{client_id}/consultations`, `PATCH /consultations/{consultation_id}/transcript`, `POST /consultations/{consultation_id}/transcript/confirm` |
| P5 | `GET /consultations/{consultation_id}/counseling-note`, `PATCH /consultations/{consultation_id}/counseling-note`, `POST /consultations/{consultation_id}/counseling-note/confirm` |
| P6 | `GET /consultations/{consultation_id}/analysis`, `GET /clients/{client_id}/actions`, `PATCH /actions/{action_id}` |
| P7 | `POST /clients/{client_id}/case-report` |

## 8. 테스트·수용 기준

### 8.1 자동화 테스트

- **단위 — `tests/unit/`:** 상태별 허용 연산, 문자열 trim·상한, 6개 상태 키, PATCH 생략/null/빈 배열, 날짜 계산, AI 스키마·인용, 예외 매핑.
- **통합 — `tests/integration/`:** 실제 PostgreSQL에서 FK·unique·행 잠금, 두 확정의 경쟁, PATCH와 확정 경쟁, 작업 예약 롤백, lease 탈취 후 오래된 실행 차단, 부분 결과 롤백, N+1 방지.
- **계약 — `tests/contract/`:** 15개 엔드포인트의 성공·오류 응답, Location·status_url, UTC Z, 양의 ID, 알 수 없는 필드 422, 검색·필터·total·안정 정렬, 미생성과 실패 구분.
- **E2E — `tests/e2e/`:** 합성 음성과 fake 공급자로 전체 흐름을 반복 검증한다. 실제 공급자 smoke test는 별도 명시적 실행과 비용 제한으로 구분한다.
- **장애 주입:** STT·LLM timeout/5xx/잘못된 JSON, DB 커밋 실패, 작업 중 프로세스 종료, 파일 유실·삭제 실패, 요청 응답 유실, 리포트 timeout을 검증한다.
- 핵심 서비스·상태 전이 모듈의 커버리지 80% 이상을 목표로 하고, 허용/금지 상태 전이는 전부 테스트한다. 커버리지 수치만으로 품질을 판단하지 않는다.

### 8.2 필수 두 상담 데모

1. 가명 내담자를 등록한다.
2. 첫 상담 음성을 업로드하고 전사문을 수정·확정한다. 전사문 PATCH 직후에는 상담일지가 없어야 한다.
3. 상담일지 초안을 확인·수정·확정한다. 확정 전에는 Risk·Action이 없어야 한다.
4. 첫 분석 완료 후 비교 상담 ID가 비어 있고 근거 없는 변화가 UNKNOWN인지 확인한다.
5. 더 나중 시각의 두 번째 상담을 업로드하고 같은 검토 절차를 진행한다.
6. 두 번째 상담일지의 식사 관련 내용을 수정·삭제하는 예제를 넣고, 원래 초안의 주장이 후속 분석에서 복원되지 않는지 확인한다.
7. 첫 상담이 비교 ID에 포함되고 근거 있는 변화·Risk·Action만 반환되는지 확인한다.
8. Action을 DONE, DISMISSED, TODO로 변경하고 목록·분석 응답·내담자 집계가 일치하는지 확인한다.
9. 두 상담을 포함한 리포트를 생성하고 상담일 순 timeline과 미확인 지원 현황의 빈 배열을 확인한다.
10. 성공·실패 테스트 종료 후 임시 음성 잔존 여부를 확인한다.

## 9. 보안·운영·배포 준비

### 9.1 데모 보안 경계

- 로그인 없는 공용 데이터 MVP이므로 실제 개인정보·실제 상담 음성을 투입하지 않는다. 가명뿐 아니라 내용도 합성 데이터를 사용한다.
- CORS는 인증이나 접근 제어가 아니다. 허용 프론트엔드 origin만 설정하되, 실데이터 공개 서비스로 전환하려면 별도의 인증·기관 격리·접근 통제·보관 정책 설계가 선행되어야 한다.
- 외부 AI에는 필요한 최소 자료만 전달한다. 공급자의 데이터 처리·보관 조건과 사용자 동의 절차는 실데이터 도입 전 별도로 검토한다. 이 문서는 법적 적합성 판단을 하지 않는다.
- 요청 본문·전사문·상담일지·프롬프트·음성·API 키는 로그에 남기지 않는다. ID·단계·소요 시간·오류 코드·모델/프롬프트 버전·사용량 등 운영 메타데이터만 남긴다.
- API 키와 DB URL은 환경 변수로 관리하고 `.env.example`에는 자리표시자만 둔다. 업로드 저장소는 비공개이고 DB는 최소 권한으로 연결한다.
- 공개 데모의 비용 남용 방지를 위해 동시 작업·대기열 크기·일별 AI 예산을 제한한다. 수용 능력 초과는 접수 전 503으로 거절한다. 별도 429 rate limit이 필요하면 API 계약을 먼저 보완한다.

### 9.2 환경 설정 목록

`APP_ENV`, `DATABASE_URL`, `CORS_ORIGINS`, `OPENAI_API_KEY`, `OPENAI_STT_MODEL`, `OPENAI_LLM_MODEL`, `AUDIO_TEMP_DIR`, `MAX_AUDIO_BYTES`, `MAX_AUDIO_SECONDS`, `JOB_CONCURRENCY`, `JOB_MAX_ATTEMPTS`, `JOB_LEASE_SECONDS`, 단계별 timeout, `CASE_REPORT_TIMEOUT_SECONDS`, `LOG_LEVEL`을 관리한다. 공급자는 OpenAI로 고정하므로 공급자 선택 환경 변수는 두지 않는다. 형식 허용 목록·대기열 상한·예산도 검증 가능한 설정으로 둔다.

필수 설정 누락은 시작 시 실패시킨다. 실제 패키지 버전과 설정 기본값은 P0/P1 산출물에 고정하며, `OPENAI_API_KEY`가 없는 CI에서는 fake 모드를 명시한다. 키는 서버 환경에만 저장하며 문서·소스 코드·프론트엔드에 포함하지 않는다.

### 9.3 배포·관측·복구

- Railway 빌드 루트는 `backend/`, 포트는 제공되는 `PORT`에 맞춘다. 마이그레이션은 배포 시 한 번만 실행하고 API 프로세스마다 수행하지 않는다.
- API와 작업 실행기를 같은 인스턴스에 두고 프로세스 수를 1로 고정한다. 종료 시 새 작업 선점을 중단하고 제한 시간 동안 진행 작업을 마무리한다.
- Railway 배포 저장소는 임시적이므로 원본 파일을 재배포 이후 복구할 수 있다고 가정하지 않는다. [Railway 배포 저장소 문서](https://docs.railway.com/deployments/reference#ephemeral-storage)
- `/health/live`는 프로세스 생존, `/health/ready`는 DB·마이그레이션·실행기 준비 상태를 확인하도록 제안한다. 제품 API와 별도의 운영 엔드포인트로 문서화한다.
- Railway의 배포 healthcheck만으로 상시 감시를 대체하지 않는다. 공식 문서상 배포 이후 지속 감시 기능은 아니므로 별도 모니터링을 준비한다. [Railway Healthchecks](https://docs.railway.com/deployments/healthchecks)
- 관측 항목: API 지연·오류율, 단계별 처리 시간·실패율, 대기 작업 수·최장 대기 시간, heartbeat 지연, 임시 디스크 사용·삭제 실패, AI 사용량·비용.
- 성능 목표 초안: 외부 AI·파일 전송을 제외한 일반 조회/수정 p95 500ms 이내, 파일 검증 완료 후 예약 응답 p95 1초 이내. 가명 내담자 100명·상담 1,000건·동시 API 요청 5건으로 측정하고 배포 환경에서 조정한다. STT·LLM 목표 시간은 공급자 실측 후 확정한다.
- DB 백업 방식·주기·보관 기간과 복원 절차를 배포 전 확인하고 별도 테스트 DB로 복원 검증한다. 백업 자동 제공을 가정하지 않는다. 원본 음성은 백업 대상이 아니다.
- 배포 전 백업과 마이그레이션 호환성을 확인한다. 롤백은 이전 앱 이미지 복귀를 우선하고 데이터 손실 가능성이 있는 DB downgrade를 자동 실행하지 않는다.

## 10. 구현 전 결정할 항목

| 항목 | 결정 기준·시점 |
| --- | --- |
| OpenAI STT 모델 ID | 공급자는 OpenAI로 확정. 한국어 상담 정확도, 화자 구분, 허용 형식·길이, 처리 시간·비용을 P0에서 합성 음성으로 검증 |
| OpenAI LLM 모델 ID | 공급자는 OpenAI로 확정. Responses API·Structured Outputs 지원, 상담자 수정 반영, 인용 정확성, 컨텍스트 한도·비용을 P0에서 검증 |
| 업로드 허용 목록·최대 용량·길이 | STT와 서버 자원 중 더 작은 한도에 맞춤. P4 전에 API 명세에 반영 |
| 세부 런타임·라이브러리 버전 | 제공자 SDK·배포 이미지 호환성 검증 후 P1에서 잠금 |
| 작업 테이블·단일 인스턴스 설계 | 본 계획의 제안 채택 여부와 재배포 중 STT 실패 수용 확인. P2 전에 결정 기록 |
| 재시도·timeout·임시 파일 최대 수명 | 전체 처리 시간·lease·삭제 정책을 모순 없이 설정. P4 전에 확정 |
| AI 입력/출력 크기와 리포트 한도 | 최대 전사·이력·현재 Action/Risk 입력을 누락 없이 처리할 수 있는지 검증. P5/P7 전에 확정 |
| 데모 노출·운영 예산·보관 기간 | 합성 데이터만 사용, 호출 예산과 공개 기간, DB·로그·백업 정리 기준. 배포 전에 확정 |

이 항목들은 계획 문서 작성의 장애물이 아니라 후속 구현의 결정 지점이다. 미정 값을 사실처럼 고정하거나 외부 서비스를 임의로 생성·결제하지 않는다.

## 11. 최종 완료 체크리스트

- [ ] API 명세의 15개 엔드포인트가 구현되어 계약 테스트를 통과한다.
- [ ] 전사문과 상담일지의 저장·확정이 분리되고 확정 후 변경이 차단된다.
- [ ] 최종 상담일지 수정이 후속 분석에 반영되며 위험신호 근거를 검증한다.
- [ ] 동시 중복 확정·작업 중복·부분 DB 실패에서 결과가 중복되거나 일부만 노출되지 않는다.
- [ ] FAILED 및 미생성 결과를 구분하고 이미 저장된 결과를 유지한다.
- [ ] 작업 재시작·파일 유실을 처리해 상담이 영구 진행 상태에 남지 않는다.
- [ ] 실제 상담일·한국 날짜 기한·과거 상담 비교·Action 집계가 일치한다.
- [ ] 성공·실패·재시작 경로에서 음성 파일 정리가 검증된다.
- [ ] 두 상담 데모와 사례회의 리포트가 끝까지 동작한다.
- [ ] 합성 데이터 사용, 비밀정보 관리, 비용 제한, health·로그·백업·롤백 준비를 마친다.

첫 구현 단위는 **P0 결정 기록과 P1 실행 기반**이다. 현재 작업에서는 이 계획 문서만 생성하며 패키지 설치, 서버 구현, 외부 공급자 호출, 배포는 수행하지 않는다.
