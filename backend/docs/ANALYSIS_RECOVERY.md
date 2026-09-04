# ANALYZING 정체 수정 및 기존 작업 복구

## 수정 내용

- 상담일지와 후속 분석에 OpenAI Structured Outputs(JSON Schema)를 지정한다.
- DB 저장 전 Pydantic으로 모든 필드·배열·enum·기한을 검증한다. 문자열 Action,
  누락 필드, 잘못된 타입은 저장하지 않는다.
- `OPENAI_TIMEOUT_SECONDS` 기본 45초, SDK 자동 재시도 없음.
- `JOB_TIMEOUT_SECONDS` 기본 120초로 AI 호출과 결과 저장을 포함한 작업을 제한한다.
- 예외 발생 시 결과 트랜잭션을 롤백하고 **새 세션**으로 FAILED를 저장한다.
  기존 전사문·상담일지·확정 시각은 보존한다. 실패 기록도 DB 장애로 저장하지
  못하면 최대 3회 시도하고 `job_failure_save_failed`를 기록한다.
- 로그에는 작업 ID와 예외 타입만 남긴다. 예외 원문, SQL 인자, AI 응답은 기록하지 않는다.
- 정상 완료 시 `job_completed`, 오류 시 `job_failed`를 남긴다.

## 상담 1번 등 이전 버전에서 중단된 작업

배포된 기존 작업의 실제 OpenAI 응답은 로그에 없어 장애 원인을 확정할 수 없다.
로컬에서는 문자열 Action의 AttributeError 및 롤백 후 만료된 ORM 객체 접근 오류를
재현했으며 두 경로가 상담을 ANALYZING에 남기는 것을 확인했다.

새 코드는 기존 RUNNING 작업을 자동으로 다시 실행하지 않는다. 이전 프로세스가
늦게 결과를 저장할 수 있으므로, **수정 버전 배포가 완료되고 이전 배포가 완전히
종료된 뒤** 아래 명령을 새 컨테이너의 `/app`에서 실행한다. Railway PostgreSQL의
DATABASE_URL이 설정된 서비스 환경에서 실행해야 한다. 로컬 기본 SQLite로 실행하면
운영 데이터에는 영향을 주지 않는다.

먼저 읽기 전용 확인:

```bash
python -m app.recover_jobs --consultation-id 1
```

`eligible`이면 이전 배포 종료를 확인한 후 재예약:

```bash
python -m app.recover_jobs --consultation-id 1 --apply --previous-deployment-stopped
```

복구는 해당 작업의 RUNNING을 QUEUED로 바꾼다. 확정 시각이나 상담 내용을 수정하지
않는다. 현재 worker가 예약된 작업을 처리한다. DONE/FAILED 상담, 부분 결과가 있는
상담, 수정된 worker가 이미 처리 중인 작업은 거절한다. 이미 QUEUED이면 변경하지 않는다.
MVP의 일반 사용자용 재분석 API는 추가하지 않았다.

복구 후 `GET /consultations/1`에서 DONE 또는 FAILED를 확인한다. DONE이면
`GET /consultations/1/analysis`가 200이다. FAILED이면 Deploy Logs의 `job_failed`에서
예외 타입을 확인한다. 기존 상담일지 조회는 계속 가능하다.

## 검증 범위

자동 테스트는 합성 데이터·SQLite·mock OpenAI로 실행한다. 실제 OpenAI 호출,
PostgreSQL 운영 DB 변경, GitHub push, Railway 재배포는 이 코드 수정 검증에 포함하지 않는다.
