# 사회복지 상담 AX Tool — MVP API 명세서

기준 문서: [MVP 기능 명세서](./SPEC.md)

이 문서는 구현할 API 계약을 정의한다. 실제 구현·배포가 완료되었다는 의미는 아니다. 기능 명세에 없는 응답 구조, 검증 규칙, 페이지네이션, 비동기 처리 방식은 아래와 같이 설계한다. 녹음 파일의 허용 형식·용량·길이는 STT 제공자 선정 후 확정한다.

## 1. 공통 규칙

| 항목 | 규칙 |
| --- | --- |
| 기본 URL | 배포 시 결정. 아래 경로는 서버 루트 기준 |
| 인증 | MVP에서는 인증 및 로그인 API 없음. 내담자는 공용 데이터 |
| 전송 | HTTPS, UTF-8 |
| 요청 형식 | 기본 `application/json`, 녹음 파일 업로드만 `multipart/form-data` |
| 응답 형식 | `application/json` |
| ID | 양의 정수. 경로의 `client_id`, `consultation_id`, `action_id`에 공통 적용 |
| 날짜·시간 | 시간대가 포함된 ISO 8601 입력. 응답은 UTC `Z` 표기 |
| 날짜 | `YYYY-MM-DD`. Action 기한은 `Asia/Seoul` 날짜 기준 |
| 필드 표기 | `snake_case` |
| 빈 값 | 미생성·미확정 단일 값은 `null`, 생성 완료 후 항목이 없는 목록은 `[]` |
| 수정 | 명시된 필드만 변경. 알 수 없는 필드는 `422` |
| 확정 | 저장된 내용을 확정한다. 수정 저장 완료 후 확정 API를 호출 |

문자열 길이는 앞뒤 공백을 제거한 뒤 문자 수로 검증한다. 선택 필드의 생략은 기본값 적용, PATCH에서 생략은 기존 값 유지다. 명시적으로 허용하지 않은 `null`은 받지 않는다.

### 목록 응답

목록 API는 `limit`(기본 20, 1~100), `offset`(기본 0, 0 이상)을 받는다. 별도 명시가 없으면 요청 본문은 없다.

```json
{
  "items": [],
  "total": 0,
  "limit": 20,
  "offset": 0
}
```

`total`은 필터 적용 후 전체 건수다. 존재하는 내담자의 기록이 없으면 `200`과 빈 목록을 반환하고, 내담자 자체가 없으면 `404`를 반환한다.

### HTTP 상태 코드

| 코드 | 의미 |
| --- | --- |
| `200` | 조회·수정 또는 동기 생성 성공 |
| `201` | 내담자 생성 완료 |
| `202` | 업로드 또는 확정 요청 접수 및 비동기 작업 예약 완료 |
| `404` | 요청한 내담자·상담·Action이 없음 |
| `409` | 허용되지 않은 상태, 중복 확정, 결과 미생성, 분석 실패 또는 입력 기록 부족 |
| `413` | 녹음 파일 허용 용량 초과 |
| `415` | 지원하지 않는 녹음 파일 형식 |
| `422` | 요청 값·필수 필드·파일 내용 검증 실패 |
| `502` | 동기 사례회의 리포트 생성 중 외부 AI 서비스 오류 |
| `503` | 작업 예약 등 서버가 요청을 접수할 수 없는 상태 |
| `504` | 동기 사례회의 리포트 생성 제한 시간 초과 |
| `500` | 예상하지 못한 서버 오류 |

## 2. 호출 순서와 상태 전이

| 순서 | 사용자 업무 | API | 결과 |
| --- | --- | --- | --- |
| 1 | 접속 후 내담자 조회·등록 | `GET /clients`, `POST /clients` | 내담자 ID 확보 |
| 2 | 상담 후 녹음 파일 업로드 | `POST /clients/{client_id}/consultations` | 상담 생성, STT 시작 |
| 3 | STT 결과 확인 | `GET /consultations/{consultation_id}` | 전사문 조회 |
| 4 | 전사문 수정·저장 | `PATCH /consultations/{consultation_id}/transcript` | 수정 내용 저장 |
| 5 | 전사문 확정 | `POST /consultations/{consultation_id}/transcript/confirm` | 상담일지 초안 생성 시작 |
| 6 | 상담일지 확인·수정 | `GET`, `PATCH /consultations/{consultation_id}/counseling-note` | 검토한 상담일지 저장 |
| 7 | 상담일지 확정 | `POST /consultations/{consultation_id}/counseling-note/confirm` | 위험신호·추천 Action 등 후속 분석 시작 |
| 8 | 결과 확인 | `GET /consultations/{consultation_id}/analysis` | 저장된 후속 분석 결과 조회 |

수정 사항이 없으면 PATCH를 생략하고 확정할 수 있다. PATCH 자체는 AI 작업을 실행하지 않는다.

```text
UPLOADED → TRANSCRIBING → AWAITING_TRANSCRIPT_REVIEW
                                  │ 전사문 확정
                                  ▼
                         GENERATING_NOTE → AWAITING_NOTE_REVIEW
                                                  │ 상담일지 확정
                                                  ▼
                                               ANALYZING → DONE
```

| 상태 | 허용되는 변경 | 다음 상태 |
| --- | --- | --- |
| `UPLOADED` | 작업 실행기가 STT 시작 | `TRANSCRIBING` |
| `TRANSCRIBING` | STT 결과 저장 | `AWAITING_TRANSCRIPT_REVIEW` |
| `AWAITING_TRANSCRIPT_REVIEW` | 전사문 수정 또는 확정 | 확정 시 `GENERATING_NOTE` |
| `GENERATING_NOTE` | 상담일지 초안 저장 | `AWAITING_NOTE_REVIEW` |
| `AWAITING_NOTE_REVIEW` | 상담일지 수정 또는 확정 | 확정 시 `ANALYZING` |
| `ANALYZING` | 후속 분석 결과 저장 | `DONE` |
| `DONE` | 조회 및 별도 Action 상태 수정 | 상담 상태 유지 |
| `FAILED` | 조회 | MVP에 수동 재실행 API 없음 |

작업 예약 이후 업로드 처리·STT·상담일지 생성·후속 분석이 실패하면 `FAILED`로 전환한다. 확정된 전사문과 상담일지는 잠그고, 확정 전 수정 요청과 확정 요청의 상태 검사는 원자적으로 처리한다. 중복 확정은 `409`다.

### 비동기 작업 계약

- 업로드와 두 확정 API는 작업을 예약한 뒤 `202`를 반환한다. AI 처리 완료를 뜻하지 않는다.
- 응답의 `status_url`을 조회해 진행 상태를 확인한다. 예를 들어 2초 간격으로 조회하고 검토 대기·완료·실패 상태에서 폴링을 중단한다.
- 작업 예약에 실패한 요청은 `503`을 반환한다. 확정 요청이라면 기존 검토 대기 상태를 유지한다.
- 결과와 다음 상태를 함께 저장한다. 후속 분석 실패 시 RiskFlag·ActionItem 일부만 노출하지 않으며, 같은 작업이 중복 실행되어도 결과 행을 중복 생성하지 않는다.
- `FAILED`이면 `failure`를 반환한다. 이미 저장된 전사문·상담일지는 조회 가능하다. 새 업로드는 새 상담을 생성하며 실패 상담을 재실행하지 않는다.
- 업로드 요청은 호출마다 새 상담을 생성한다. 응답 유실 시 상담 목록을 확인한 뒤 재업로드 여부를 판단한다.

## 3. 공통 데이터 구조

아래 필드는 별도 표기가 없으면 응답에 항상 포함한다. 모든 예시는 가명 데이터다.

### 3.1 Client 및 ClientSummary

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | integer | 내담자 ID |
| `name` | string | 이름 또는 가명 |
| `birth_year` | integer 또는 null | 출생연도 |
| `gender` | string 또는 null | `F`, `M`, `OTHER`, `UNKNOWN` |
| `memo` | string 또는 null | 메모 |
| `created_at` | datetime | 등록 시각 |

`ClientSummary`는 Client에 다음 필드를 추가한다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `last_consulted_at` | datetime 또는 null | 가장 최근 상담일. 실패 상담 제외 |
| `pending_action_count` | integer | 해당 내담자의 `TODO` Action 수 |
| `has_important_risk` | boolean | `resolved=false`이며 `severity=HIGH`인 위험신호 존재 여부 |

### 3.2 Consultation

```json
{
  "id": 101,
  "client_id": 1,
  "consulted_at": "2026-09-04T01:00:00Z",
  "transcript": "사회복지사: 요즘 식사는 잘하고 계세요?\n김OO: 무릎이 아파서 식사 준비가 힘들어요.",
  "transcript_confirmed_at": null,
  "counseling_note_confirmed_at": null,
  "status": "AWAITING_TRANSCRIPT_REVIEW",
  "failure": null,
  "created_at": "2026-09-04T01:30:00Z"
}
```

`transcript`는 전사 완료 전 `null`이다. 두 확정 시각은 확정 API 접수 시 기록한다. `failure`는 실패 외에는 `null`이며 실패 시 다음 형태다.

```json
{
  "stage": "TRANSCRIBING",
  "code": "STT_FAILED",
  "message": "녹음 파일을 전사하지 못했습니다."
}
```

실패 `stage`는 `UPLOADED`, `TRANSCRIBING`, `GENERATING_NOTE`, `ANALYZING` 중 하나다. 오류 코드는 `UPLOAD_PROCESSING_FAILED`, `STT_FAILED`, `NOTE_GENERATION_FAILED`, `ANALYSIS_FAILED`로 대응한다. 내부 예외나 외부 서비스 응답 원문은 노출하지 않는다.

### 3.3 ClientStatus

```json
{
  "health": ["무릎 통증 지속"],
  "nutrition": ["식사 준비 어려움"],
  "emotion": [],
  "family": [],
  "housing": [],
  "social": []
}
```

6개 키는 항상 포함하며 각 값은 문자열 배열이다. 객체 키는 소문자를 사용하고, 상태변화의 `category`는 `HEALTH`, `NUTRITION`, `EMOTION`, `FAMILY`, `HOUSING`, `SOCIAL`을 사용한다.

### 3.4 CounselingNote

```json
{
  "consultation_id": 101,
  "summary": "무릎 통증으로 식사 준비에 어려움을 호소함.",
  "main_contents": ["무릎 통증 지속", "식사 준비 어려움"],
  "client_status": {
    "health": ["무릎 통증 지속"],
    "nutrition": ["식사 준비 어려움"],
    "emotion": [],
    "family": [],
    "housing": [],
    "social": []
  },
  "confirmed_at": null,
  "created_at": "2026-09-04T01:35:00Z"
}
```

`confirmed_at`은 상담일지 확정 시각이며 상담 응답의 `counseling_note_confirmed_at`과 같다. 위험신호·추천 Action은 상담일지 초안에 포함하지 않는다.

### 3.5 RiskFlag

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id`, `consultation_id` | integer | 위험신호 및 상담 ID |
| `type` | enum | `HEALTH`, `NUTRITION`, `EMOTION`, `ISOLATION`, `ABUSE`, `HOUSING`, `ECONOMIC`, `SAFETY`, `OTHER` |
| `severity` | enum | `LOW`, `MEDIUM`, `HIGH` |
| `description` | string | 추가 확인이 필요한 내용. 확정 진단 금지 |
| `evidence` | string 또는 null | 확정 전사문에서 인용한 근거. 인용할 수 없으면 null |
| `resolved` | boolean | 생성 시 false. MVP에는 별도 변경 API 없음 |
| `created_at` | datetime | 생성 시각 |

상담일지에 상담자가 추가한 내용을 전사문 인용인 것처럼 반환하지 않는다.

### 3.6 ActionItem

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id`, `client_id`, `consultation_id` | integer | Action 및 관련 ID |
| `action_type` | enum | 아래 Action 유형 |
| `title` | string | 할 일 제목 |
| `description` | string 또는 null | 상세 설명 |
| `priority` | enum | `HIGH`, `MEDIUM`, `LOW` |
| `reason` | string | 추천 사유 |
| `due_date` | date 또는 null | 권장 기한. 판단 근거 없으면 null |
| `status` | enum | `TODO`, `DONE`, `DISMISSED`. 생성 시 TODO |
| `created_at` | datetime | 생성 시각 |

Action 유형: `FOLLOW_UP_CALL`, `HOME_VISIT`, `CONTACT_FAMILY`, `CONTACT_SUPPORT_WORKER`, `RESOURCE_REFERRAL`, `CASE_REVIEW`, `CHECK_HEALTH`, `CHECK_NUTRITION`, `OTHER`.

기능 명세의 `due_in_days`는 AI 내부 생성값이다. API에서는 상담일의 한국 날짜에 해당 일수를 더한 `due_date`로 반환한다. 과거 상담 업로드라면 기한도 과거일 수 있으며, 업로드일 기준으로 임의 이동하지 않는다.

## 4. 내담자 API

### 4.1 내담자 등록

`POST /clients`

| 요청 필드 | 타입 | 필수 | 검증 |
| --- | --- | --- | --- |
| `name` | string | 예 | 1~100자 |
| `birth_year` | integer 또는 null | 아니요 | 1900~현재 연도, 기본 null |
| `gender` | enum 또는 null | 아니요 | Client의 gender 값, 기본 null |
| `memo` | string 또는 null | 아니요 | 최대 2,000자, 기본 null |

```json
{
  "name": "김OO",
  "birth_year": 1945,
  "gender": "F",
  "memo": "독거 / 딸 부산 거주"
}
```

성공: `201`, Client 객체. `Location: /clients/{id}` 헤더를 반환한다. 동명이인은 허용한다.

오류: `422` 입력 검증 실패.

### 4.2 내담자 목록·검색

`GET /clients?search=김&limit=20&offset=0`

추가 쿼리: `search`는 선택 문자열(최대 100자)이며 이름·가명 부분 일치 검색이다. 생략하거나 공백이면 전체 조회한다.

성공: `200`, 목록 응답의 `items`는 ClientSummary 배열. `created_at DESC, id DESC` 정렬.

오류: `422` 잘못된 쿼리.

### 4.3 내담자 상세

`GET /clients/{client_id}`

성공: `200`, ClientSummary에 아래 필드를 추가한다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `current_status` | ClientStatus 또는 null | 상담일 기준 가장 최근 DONE 상담의 상태 |
| `current_status_consultation_id` | integer 또는 null | 상태 요약의 출처 상담 |
| `pending_actions` | ActionItem[] | TODO Action 중 기한 오름차순 상위 5건. 기한 null은 마지막, 동률은 id 오름차순 |
| `recent_consultations` | ConsultationSummary[] | 상담일 내림차순 상위 5건 |

전체 상담과 Action은 별도 목록 API로 조회한다. 상담이 없으면 현재 상태는 `null`, 두 목록은 `[]`다.

오류: `404` 내담자 없음, `422` 잘못된 ID.

## 5. 상담 업로드 및 조회 API

### 5.1 녹음 파일 업로드·상담 생성

`POST /clients/{client_id}/consultations`

Content-Type: `multipart/form-data`

| Form 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `audio` | binary file | 예 | 서비스 외부에서 녹음한 파일 1개 |
| `consulted_at` | datetime | 예 | 실제 상담 시각. 업로드 시각과 구분 |

파일이 비어 있거나 실제 오디오로 해석할 수 없으면 `422`다. 확장자뿐 아니라 파일 내용도 검증한다. 파일을 임시 저장하고 STT 결과 저장 후 삭제한다. 실패 시에도 임시 파일을 정리하며 원본 다운로드 API는 제공하지 않는다.

성공: `202`. 상담 리소스와 작업 예약이 생성된 뒤 반환한다.

```json
{
  "consultation_id": 101,
  "status": "UPLOADED",
  "status_url": "/consultations/101"
}
```

`Location: /consultations/101` 헤더를 반환한다.

오류: `404` 내담자 없음, `413` 용량 초과, `415` 미지원 형식, `422` 필수 필드·파일 오류, `503` 접수 실패.

**구현 전 확정 항목:** 허용 확장자·MIME·코덱, 최대 바이트 수, 최대 재생 시간. STT 제공자와 배포 환경에 맞춰 값을 결정하고 문서에 반영해야 한다.

### 5.2 상담 상세·처리 상태·전사문 조회

`GET /consultations/{consultation_id}`

성공: `200`, Consultation 객체. 처리 중·검토 대기·실패도 리소스 조회 자체는 `200`이다.

오류: `404` 상담 없음, `422` 잘못된 ID.

### 5.3 내담자 상담 이력

`GET /clients/{client_id}/consultations?limit=20&offset=0`

추가 쿼리: 선택 `status`로 상담 상태 하나를 필터링한다. 생략하면 실패·진행 중을 포함한 모든 상담을 반환한다.

성공: `200`, 목록 응답. `consulted_at DESC, id DESC` 정렬.

`ConsultationSummary` 필드:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id`, `client_id` | integer | 상담 및 내담자 ID |
| `consulted_at`, `created_at` | datetime | 상담·생성 시각 |
| `status` | enum | 상담 상태 |
| `summary` | string 또는 null | 현재 저장된 상담일지 요약. 초안 생성 전 null |
| `counseling_note_confirmed_at` | datetime 또는 null | 요약 확정 여부 판단용 |

오류: `404` 내담자 없음, `422` 쿼리·ID 오류.

## 6. 전사문 검토 API

### 6.1 전사문 수정·저장

`PATCH /consultations/{consultation_id}/transcript`

허용 상태: `AWAITING_TRANSCRIPT_REVIEW`.

```json
{
  "transcript": "사회복지사: 요즘 식사는 잘하고 계세요?\n김OO: 무릎이 아파서 식사 준비가 힘들어요."
}
```

필수 `transcript`: 비어 있지 않은 문자열, 최대 200,000자. 전체 전사문을 교체한다.

성공: `200`, 수정된 Consultation 객체. 상태는 유지하고 상담일지는 생성하지 않는다.

오류: `404` 상담 없음, `409 INVALID_STATE` 수정 불가, `422` 입력 오류.

### 6.2 전사문 확정·상담일지 초안 생성

`POST /consultations/{consultation_id}/transcript/confirm`

요청 본문 없음. 허용 상태: `AWAITING_TRANSCRIPT_REVIEW`.

저장된 전사문을 확정하고 `transcript_confirmed_at`을 기록한다. `GENERATING_NOTE`로 전환해 상담일지 생성 작업을 예약한다.

성공: `202`.

```json
{
  "consultation_id": 101,
  "status": "GENERATING_NOTE",
  "status_url": "/consultations/101"
}
```

완료 후 `AWAITING_NOTE_REVIEW`로 전환한다. 이 작업은 위험신호·상태변화·추천 Action을 생성하지 않는다.

오류: `404` 상담 없음, `409 INVALID_STATE` 중복 확정·잘못된 단계, `422` 잘못된 ID, `503` 작업 예약 실패.

## 7. 상담일지 검토 API

### 7.1 상담일지 조회

`GET /consultations/{consultation_id}/counseling-note`

성공: `200`, CounselingNote 객체. 생성된 상담일지는 후속 분석 실패 상태에서도 조회할 수 있다.

오류: `404` 상담 없음, `409 RESULT_NOT_READY` 초안 미생성, `409 PROCESSING_FAILED` 상담일지 생성 전 처리 실패, `422` 잘못된 ID.

### 7.2 상담일지 수정·저장

`PATCH /consultations/{consultation_id}/counseling-note`

허용 상태: `AWAITING_NOTE_REVIEW`.

| 요청 필드 | 타입 | 검증 |
| --- | --- | --- |
| `summary` | string | 1~5,000자 |
| `main_contents` | string[] | 최대 100개, 항목당 1~2,000자 |
| `client_status` | ClientStatus | 6개 키 필수, 각 배열 최대 100개, 항목당 1~2,000자 |

위 필드 중 하나 이상이 필요하다. 전달한 배열·객체는 전체 교체하고, 생략한 최상위 필드는 유지한다. null은 허용하지 않으며, 배열의 항목 삭제는 수정된 배열 또는 `[]`를 전달한다.

```json
{
  "summary": "무릎 통증으로 식사 준비에 어려움을 호소하며, 식사 횟수는 추가 확인이 필요함.",
  "main_contents": ["무릎 통증 지속", "식사 준비 어려움", "실제 식사 횟수는 미확인"]
}
```

성공: `200`, 수정된 CounselingNote. 위험신호·추천 Action은 생성하지 않는다.

오류: `404` 상담 없음, `409 INVALID_STATE` 수정 불가, `422` 입력 오류.

### 7.3 상담일지 확정·후속 분석

`POST /consultations/{consultation_id}/counseling-note/confirm`

요청 본문 없음. 허용 상태: `AWAITING_NOTE_REVIEW`.

저장된 상담일지를 확정하고 `counseling_note_confirmed_at`을 기록한다. 확정 상담일지를 기준으로 구조화 데이터를 갱신한 뒤 위험신호·미해결 이슈·상태변화·추천 Action을 생성한다. 확정 전사문은 근거 확인용으로 사용한다.

성공: `202`.

```json
{
  "consultation_id": 101,
  "status": "ANALYZING",
  "status_url": "/consultations/101"
}
```

최근 이전 상담은 같은 내담자의 `DONE` 상담 중 현재 `consulted_at`보다 이른 기록을 최신순 최대 5건 사용한다. 5건 미만이면 있는 만큼 사용한다. 이전 기록이 없어도 현재 상담 분석은 수행하고, 비교 근거가 없는 변화는 `UNKNOWN`으로 반환한다. 이전 기록 ID를 결과에 포함한다.

전체 결과 저장 후 `DONE`으로 전환한다. Action은 `TODO`로 생성한다. 확정 상담일지에서 수정·삭제한 내용을 예전 초안에서 가져와 위험신호나 Action으로 복원하지 않는다.

오류: `404` 상담 없음, `409 INVALID_STATE` 중복 확정·잘못된 단계, `422` 잘못된 ID, `503` 작업 예약 실패.

## 8. 후속 분석 결과 API

`GET /consultations/{consultation_id}/analysis`

성공: `200`. `DONE` 상태에서 완성된 결과를 반환한다.

```json
{
  "consultation_id": 101,
  "summary": "무릎 통증으로 식사 준비에 어려움을 호소함.",
  "client_status": {
    "health": ["무릎 통증 지속"],
    "nutrition": ["식사 준비 어려움"],
    "emotion": [],
    "family": [],
    "housing": [],
    "social": []
  },
  "compared_consultation_ids": [],
  "important_changes": [
    {
      "category": "NUTRITION",
      "change": "UNKNOWN",
      "previous": null,
      "current": "식사 준비 어려움",
      "description": "비교할 이전 상담 기록이 없어 변화 여부 확인이 필요함"
    }
  ],
  "risk_flags": [
    {
      "id": 201,
      "consultation_id": 101,
      "type": "NUTRITION",
      "severity": "MEDIUM",
      "description": "식생활 상태 추가 확인 필요",
      "evidence": "무릎이 아파서 식사 준비가 힘들어요.",
      "resolved": false,
      "created_at": "2026-09-04T01:45:00Z"
    }
  ],
  "unresolved_issues": ["식사지원 서비스 이용 여부 미확인"],
  "recommended_actions": [
    {
      "id": 301,
      "client_id": 1,
      "consultation_id": 101,
      "action_type": "CHECK_NUTRITION",
      "title": "식생활 상태 재확인",
      "description": "식사 횟수와 식사 준비 지원 필요 여부 확인",
      "priority": "HIGH",
      "reason": "식사 준비의 어려움을 호소함",
      "due_date": null,
      "status": "TODO",
      "created_at": "2026-09-04T01:45:00Z"
    }
  ],
  "created_at": "2026-09-04T01:45:00Z"
}
```

- `summary`, `client_status`는 확정 상담일지의 수정 내용을 반영한다.
- `important_changes` 항목의 `change`는 `IMPROVED`, `UNCHANGED`, `WORSENED`, `UNKNOWN`이다. `previous`, `current`는 문자열 또는 null이다. 근거가 없는 정상 상태나 변화를 만들어내지 않는다.
- `unresolved_issues`는 문자열 배열이다. `risk_flags`는 RiskFlag 배열, `recommended_actions`는 ActionItem 배열이다.
- Action ID는 Action 목록·수정 API와 동일하다. 완료 처리 후 분석 결과 조회에서도 현재 Action 상태를 반환한다.
- 후속 분석 전에는 빈 결과를 성공 응답으로 반환하지 않는다. 분석 완료 후 발견된 항목이 없는 경우에만 해당 배열을 `[]`로 반환한다.

오류: `404` 상담 없음, `409 RESULT_NOT_READY` 후속 분석 전·진행 중, `409 PROCESSING_FAILED` 처리 실패, `422` 잘못된 ID.

## 9. Action API

### 9.1 내담자 Action 목록

`GET /clients/{client_id}/actions?status=TODO&limit=20&offset=0`

| 추가 쿼리 | 타입 | 설명 |
| --- | --- | --- |
| `status` | enum | 선택. TODO, DONE, DISMISSED. 생략 시 전체 |
| `priority` | enum | 선택. HIGH, MEDIUM, LOW. 생략 시 전체 |

성공: `200`, 목록 응답의 items는 ActionItem 배열. `due_date ASC`(null 마지막), 동률은 `id ASC` 정렬.

오류: `404` 내담자 없음, `422` 입력 오류.

### 9.2 Action 상태 수정

`PATCH /actions/{action_id}`

```json
{
  "status": "DONE"
}
```

필수 `status`: `TODO`, `DONE`, `DISMISSED`. 완료·제외를 취소해 TODO로 되돌릴 수 있다. 같은 상태 요청은 변경 없이 `200`을 반환한다. MVP에서는 제목·기한·우선순위 직접 수정은 제공하지 않는다.

성공: `200`, 변경된 ActionItem. 상담의 `DONE` 상태는 바뀌지 않는다.

오류: `404` Action 없음, `422` 허용하지 않는 상태·필드.

## 10. 사례회의 리포트 API

기능 명세에 포함된 별도 종합 기능이다. 상담 한 건의 검토·확정 과정에서는 자동 호출하지 않는다.

`POST /clients/{client_id}/case-report`

```json
{
  "consultation_limit": 10
}
```

`consultation_limit`: 선택 정수, 3~10, 기본 10. 본문은 생략 가능하다. 상담일 기준 최신 `DONE` 상담을 지정 건수까지 사용하고, 현재 TODO Action과 미해결 Risk를 함께 참조한다.

DONE 상담이 1~2건이면 있는 기록만으로 생성한다. 이는 기능 명세의 두 상담 데모도 지원하기 위한 규칙이다. 0건이면 `409 INSUFFICIENT_DATA`다.

성공: `200`, 생성이 끝난 리포트를 동기 응답한다. 별도 저장·조회 API는 MVP에 포함하지 않는다.

```json
{
  "client_id": 1,
  "consultation_ids": [101, 99],
  "report": {
    "client_overview": "김OO / 1945년생 / 독거",
    "recent_status": {
      "health": ["무릎 통증 지속"],
      "nutrition": ["식사 준비 어려움"],
      "emotion": [],
      "family": [],
      "housing": [],
      "social": []
    },
    "timeline": [
      {
        "consultation_id": 99,
        "consulted_at": "2026-08-21T01:00:00Z",
        "description": "무릎 통증 확인"
      },
      {
        "consultation_id": 101,
        "consulted_at": "2026-09-04T01:00:00Z",
        "description": "식사 준비 어려움 확인"
      }
    ],
    "current_risks": ["식생활 상태 추가 확인 필요"],
    "support_status": [],
    "unresolved_issues": ["식사지원 서비스 이용 여부 미확인"],
    "discussion_points": ["식사 지원 서비스 연계 필요 여부 검토"]
  },
  "generated_at": "2026-09-04T02:00:00Z"
}
```

`recent_status`는 ClientStatus, `timeline`은 상담일 오름차순 배열이다. `client_overview`는 문자열, 나머지 보고서 항목은 문자열 배열이다. 확인되지 않은 지원 현황은 생성하지 않는다.

오류: `404` 내담자 없음, `409 INSUFFICIENT_DATA` 완료 상담 없음, `422` 요청 오류, `502` AI 서비스 실패, `504` 생성 시간 초과.

## 11. 오류 응답

모든 오류는 아래 공통 구조를 사용한다. 상태 충돌 외 오류에서 `current_status`와 `allowed_statuses`는 생략한다.

```json
{
  "error": {
    "code": "INVALID_STATE",
    "message": "전사문 검토 대기 상태에서만 수정할 수 있습니다.",
    "details": [],
    "current_status": "GENERATING_NOTE",
    "allowed_statuses": ["AWAITING_TRANSCRIPT_REVIEW"]
  }
}
```

입력 오류 예시:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "요청 값을 확인해주세요.",
    "details": [
      {
        "field": "consulted_at",
        "reason": "시간대가 포함된 상담 시각이 필요합니다."
      }
    ]
  }
}
```

| 오류 코드 | HTTP | 의미 |
| --- | --- | --- |
| `VALIDATION_ERROR` | 422 | 필드·본문·ID 검증 실패 |
| `NOT_FOUND` | 404 | 대상 리소스 없음 |
| `INVALID_STATE` | 409 | 변경 불가 상태 또는 중복 확정 |
| `RESULT_NOT_READY` | 409 | 요청한 결과가 아직 생성되지 않음 |
| `PROCESSING_FAILED` | 409 | 처리 실패로 요청한 결과를 제공할 수 없음 |
| `INSUFFICIENT_DATA` | 409 | 사례회의 리포트 입력 기록 없음 |
| `FILE_TOO_LARGE` | 413 | 최대 파일 크기 초과 |
| `UNSUPPORTED_AUDIO_FORMAT` | 415 | 지원하지 않는 오디오 형식 |
| `INVALID_AUDIO` | 422 | 빈 파일·손상된 오디오 |
| `SERVICE_UNAVAILABLE` | 503 | 요청 접수 또는 작업 예약 실패 |
| `AI_SERVICE_ERROR` | 502 | 동기 리포트 생성 중 외부 AI 오류 |
| `AI_TIMEOUT` | 504 | 동기 리포트 생성 시간 초과 |
| `INTERNAL_ERROR` | 500 | 예상하지 못한 서버 오류 |

## 12. 구현 확인 기준

- 파일 업로드 후 STT만 실행하며 전사문 확정 전 상담일지를 생성하지 않는다.
- 전사문·상담일지 PATCH는 내용을 저장하고 상태를 유지한다.
- 전사문 확정은 상담일지만 생성하고, 상담일지 확정은 후속 분석을 실행한다.
- 허용 상태 외 수정·확정 및 동시 중복 확정은 409로 처리한다.
- 상담자가 수정한 최종 상담일지가 위험신호·추천 Action에 반영된다.
- 처리 중, 검토 대기, 실패, 완료 및 결과가 없는 상태를 구분해 반환한다.
- 후속 분석 결과와 Action·Risk 저장이 완료된 경우에만 DONE으로 표시한다.
- 녹음·로그인·재분석 API는 제공하지 않는다.
