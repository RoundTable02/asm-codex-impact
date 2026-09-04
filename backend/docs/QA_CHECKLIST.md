# 백엔드 QA 체크리스트

배포 전 가명·합성 데이터와 `AI_MODE=fake`를 사용해 실행한다. 실제 개인정보·상담 음성·OpenAI API 키를 테스트 데이터나 로그에 사용하지 않는다.

## 자동 검증

- [ ] `cd backend && python3 -m pytest -q`가 통과한다.
- [ ] `python3 -m ruff format --check app tests && python3 -m ruff check app tests`가 통과한다.
- [ ] PostgreSQL 환경에서도 업로드, 상담일지 생성, 분석 저장을 한 트랜잭션 단위로 확인한다.
- [ ] 운영 환경에서 `AI_MODE=openai`와 모델·키·CORS·DB URL이 설정되어 있고 키가 응답/로그/이미지에 없음을 확인한다.

## API·업무 흐름

- [ ] `POST /clients`가 201 및 `Location` 헤더를 반환하고, 이름 공백·미래 출생연도·알 수 없는 필드를 422 처리한다.
- [ ] `GET /clients`가 검색, limit/offset, 안정 정렬과 필터 적용 `total`을 반환한다.
- [ ] WAV/MP3/M4A/OGG/WebM의 정상 합성 파일만 업로드되고 빈 파일은 422, 허용되지 않은 확장자는 415, 초과 파일은 413이다.
- [ ] 업로드가 202를 반환한 뒤 `AWAITING_TRANSCRIPT_REVIEW`까지 전이하며, 완료 후 임시 오디오가 삭제된다.
- [ ] 전사문 PATCH는 검토 대기에서만 저장되고 상담일지를 만들지 않는다.
- [ ] 전사문 확정은 202와 `GENERATING_NOTE`를 반환하며, 중복 확정과 확정 후 PATCH는 409이다.
- [ ] 상담일지 PATCH가 top-level 필드별로 저장되고, 확정 후 변경은 409이다.
- [ ] 상담일지 확정 전에 분석 결과 조회는 `RESULT_NOT_READY` 409이고, 확정 후에만 DONE 및 Risk/Action이 생성된다.
- [ ] 최종 상담일지의 수정 내용이 분석 summary/status에 반영되고 초안 내용이 되살아나지 않는다.
- [ ] Action 상태를 TODO/DONE/DISMISSED로 변경하면 Action 목록과 분석 응답에서 동일하게 보인다.
- [ ] 완료 상담 0건의 사례회의 리포트는 `INSUFFICIENT_DATA` 409, 1~10건은 200이며 timeline은 상담일 오름차순이다.

## 장애·보안·운영

- [ ] STT/LLM 오류 시 상담이 FAILED가 되고, 이미 저장된 전사문·상담일지는 계속 조회 가능하다.
- [ ] AI 응답의 evidence가 전사문에 없는 경우 null로 저장된다.
- [ ] OpenAI 실패 원문, DB URL, 전사문, 상담일지, 음성 바이트가 로그나 오류 응답에 없다.
- [ ] `CORS_ORIGINS`는 배포 프론트엔드 origin만 포함하고 `*`가 아니다.
- [ ] `/health/live`와 `/health/ready`가 배포 healthcheck에서 200을 반환한다.
- [ ] Railway PostgreSQL 백업/복원 절차와 앱 이미지 롤백 절차를 테스트 DB에서 검증한다.
- [ ] Railway는 단일 API 프로세스로 실행하며, 재배포 중 처리 중인 STT가 실패 처리되는지 확인한다.

## 실 OpenAI 배포 스모크 테스트

- [ ] 짧은 합성 한국어 음성을 1건 업로드해 STT 모델의 형식·시간·비용을 기록한다.
- [ ] 전사문/상담일지/분석/리포트 Structured JSON이 계약 스키마를 만족하는지 확인한다.
- [ ] 요청당 비용, 동시 작업 수, 장애 알림 기준을 운영 예산에 맞게 설정한다.
