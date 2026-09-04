# 이음노트 — 사회복지 상담 AX Tool

사회복지사가 어르신과의 전화 상담 후 수행하는 기록·정리 업무를 AI로 보조하는 MVP입니다. 상담 녹음 업로드부터 전사문 검토, 상담일지 작성, 위험 신호 및 후속 조치 추천까지의 흐름을 지원합니다.

> 해커톤 MVP입니다. 실제 개인정보를 입력하거나, AI 결과를 의료·법률적 판단으로 사용해서는 안 됩니다.

## 주요 기능

- 내담자 등록, 목록 조회 및 이름·가명 검색
- 상담 녹음 파일 업로드 및 STT 전사
- 전사문과 상담일지의 검토·수정·확정 분리
- 위험 신호, 미해결 이슈, 상태 변화 및 후속 Action 추천
- 내담자별 상담 이력, 미완료 Action, 사례회의 리포트 조회

## 처리 흐름

```text
내담자 등록/선택
  → 녹음 파일 업로드
  → 전사문 생성 및 검토
  → 상담일지 초안 생성 및 검토
  → 위험 신호·후속 Action 분석
  → 이력 및 사례회의 리포트 확인
```

상담은 아래 상태로 진행됩니다.

```text
UPLOADED → TRANSCRIBING → AWAITING_TRANSCRIPT_REVIEW
          → GENERATING_NOTE → AWAITING_NOTE_REVIEW
          → ANALYZING → DONE
```

## 구성

| 경로 | 설명 |
| --- | --- |
| `frontend/` | 빌드 도구 없이 동작하는 정적 HTML UI 시안 |
| `backend/` | FastAPI, SQLAlchemy 기반 API 및 비동기 작업 워커 |
| `docs/SPEC.md` | MVP 기능 명세 |
| `docs/API_SPEC.md` | API 계약과 상태 전이 명세 |
| `backend/docs/` | 배포, QA, 장애 복구 관련 문서 |

## 빠른 시작

### 1. 프런트엔드 보기

프런트엔드는 현재 하드코딩된 데모 데이터로 동작하는 UI 시안입니다.

```bash
cd frontend
python3 -m http.server 5173
```

브라우저에서 `http://localhost:5173`을 엽니다.

### 2. 백엔드 실행

Python 3.11 이상이 필요합니다. 기본 설정은 SQLite를 사용하며, 로컬에서 실제 OpenAI 호출 없이 흐름을 확인하려면 `AI_MODE=fake`를 설정합니다.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

export AI_MODE=fake
uvicorn app.main:app --reload
```

API는 `http://localhost:8000`에서 실행됩니다. 상태 확인 엔드포인트는 다음과 같습니다.

```bash
curl http://localhost:8000/health/ready
```

실제 AI를 사용하려면 `backend/.env.example`을 참고해 `OPENAI_API_KEY`를 설정하고 `AI_MODE=openai`로 실행하세요. 프로덕션에서는 `CORS_ORIGINS`를 프런트엔드 Origin으로 제한해야 합니다.

### Docker Compose로 실행

PostgreSQL과 API를 함께 실행하려면 다음과 같이 환경 파일을 준비합니다.

```bash
cd backend
cp .env.example .env
# .env에서 DATABASE_URL, OPENAI_API_KEY 등 필요한 값을 설정
docker compose up --build
```

`compose.yaml`의 기본 API 포트는 `8000`, PostgreSQL 포트는 `5432`입니다.

## 테스트와 정적 검사

```bash
cd backend
source .venv/bin/activate
pytest
ruff check .
```

계약 테스트는 `AI_MODE=fake`와 임시 SQLite 데이터베이스를 사용하므로 OpenAI API 키가 필요하지 않습니다.

## API 개요

| 목적 | 엔드포인트 |
| --- | --- |
| 내담자 등록·목록 | `POST /clients`, `GET /clients` |
| 상담 업로드·조회 | `POST /clients/{client_id}/consultations`, `GET /consultations/{consultation_id}` |
| 전사문 검토·확정 | `PATCH /consultations/{consultation_id}/transcript`, `POST /consultations/{consultation_id}/transcript/confirm` |
| 상담일지 검토·확정 | `GET/PATCH /consultations/{consultation_id}/counseling-note`, `POST /consultations/{consultation_id}/counseling-note/confirm` |
| 분석·후속 조치 | `GET /consultations/{consultation_id}/analysis`, `GET /clients/{client_id}/actions`, `PATCH /actions/{action_id}` |
| 사례회의 리포트 | `POST /clients/{client_id}/case-report` |

전체 요청·응답 형식과 오류 규칙은 [API 명세](docs/API_SPEC.md)를 참고하세요.

## 배포

- 프런트엔드: 루트의 `vercel.json`이 `frontend/`를 정적 배포 경로로 지정합니다.
- 백엔드: Railway 등에서 서비스 루트를 `backend`로 설정하고 Dockerfile로 빌드합니다.

상세 절차와 운영 전 점검 사항은 [배포 안내](backend/docs/DEPLOYMENT.md), [QA 체크리스트](backend/docs/QA_CHECKLIST.md)를 참고하세요.

## 유의사항

- MVP에는 로그인·권한 관리가 없으므로 데이터는 공용으로 취급됩니다.
- 데모에서는 반드시 가명 및 비식별화된 녹음·상담 데이터를 사용하세요.
- AI가 생성한 위험 신호와 추천 Action은 상담자의 검토를 위한 보조 정보이며, 확정 진단이나 전문 판단을 대체하지 않습니다.
