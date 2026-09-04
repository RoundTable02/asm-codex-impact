# 이음노트 — 프론트엔드

사회복지 상담 기록 도구 UI 시안. 빌드 도구 없이 동작하는 **단일 정적 HTML**입니다.

## 구성

| 파일 | 설명 |
|---|---|
| `index.html` | 5개 화면(내담자 목록 · 상세 · 상담 처리 · 사례회의 리포트 · 디자인 토큰) 전체 |

- 외부 의존성: Google Fonts(Noto Sans KR, IBM Plex Mono) 뿐. 번들러·프레임워크 없음
- 다크모드: `prefers-color-scheme` 자동 + 상단 `◐ 테마` 버튼으로 수동 전환
- 화면 전환은 좌측 내비, 상담 처리 단계 전환은 좌측 단계 레일 클릭
- 데이터는 전부 하드코딩된 더미. API 연동 지점은 화면 안에 `GET /clients` 형태의 코드 칩으로 표시해 둠

## 로컬에서 보기

```bash
cd frontend && python3 -m http.server 5173
# http://localhost:5173
```

## 배포

**Vercel (권장)** — 저장소 루트의 `vercel.json`이 `frontend/`를 정적 루트로 지정합니다.

```bash
npx vercel --prod        # 저장소 루트에서 실행
```

**GitHub Pages** — Settings → Pages → Source를 `main` 브랜치 `/docs`로 지정한 뒤
`index.html`을 `docs/`로 복사하거나 심볼릭 링크를 두면 됩니다.

## 다음 단계

이 시안을 실제 프론트로 옮길 때는 `docs/API_SPEC.md`의 상태 전이
(`UPLOADED → TRANSCRIBING → AWAITING_TRANSCRIPT_REVIEW → ... → DONE`)를 기준으로
"상담 처리" 화면부터 컴포넌트화하는 것을 권합니다. 초안/확정 구분(점선/실선)이
이 제품의 핵심 규칙이므로 디자인 토큰 화면의 정의를 그대로 유지해 주세요.
