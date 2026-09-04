# 배포 안내

Railway 서비스의 Root Directory를 `backend`로 설정하고 Dockerfile로 빌드한다. PostgreSQL 플러그인을 추가한 뒤 `DATABASE_URL`을 `postgresql+asyncpg://` 형식으로 설정한다.

필수 환경 변수는 `.env.example`을 따른다. 해커톤 데모에서는 `CORS_ORIGINS=*`로 모든 Origin을 허용한다. 실제 개인정보를 다루는 서비스로 전환하기 전에는 프론트엔드 Origin만 지정해야 한다. 운영에서는 `AI_MODE=openai`, `OPENAI_API_KEY`, OpenAI 모델 ID를 반드시 설정한다. API 프로세스는 작업 실행기도 함께 수행하므로 인스턴스를 하나만 실행한다.

배포 healthcheck는 `/health/ready`로 지정한다. 현 구현은 시작 시 스키마를 생성하며, 운영 마이그레이션은 Alembic을 도입해 배포 작업에서 한 번만 실행하도록 전환해야 한다. 실제 배포 전에는 [QA 체크리스트](./QA_CHECKLIST.md)를 모두 완료한다.
