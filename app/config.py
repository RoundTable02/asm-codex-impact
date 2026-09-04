"""애플리케이션 설정.

API_SPEC 5.1의 "구현 전 확정 항목"(허용 확장자·MIME·최대 용량·최대 재생 시간)을
여기에서 확정한다. STT 제공자를 바꿀 때 이 값만 조정하면 된다.
"""

from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

KST = ZoneInfo("Asia/Seoul")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 로컬은 SQLite, 배포(Railway)는 postgresql+psycopg://... 로 교체한다.
    database_url: str = "sqlite:///./asm_codex_impact.db"

    # AI 어댑터: "mock" 또는 "openai"
    ai_provider: str = "mock"
    openai_api_key: str | None = None
    openai_stt_model: str = "whisper-1"
    openai_llm_model: str = "gpt-4o-mini"

    # 사례회의 리포트는 동기 생성이므로 제한 시간을 둔다(초과 시 504 AI_TIMEOUT).
    case_report_timeout_seconds: float = 30.0

    # ---- 녹음 파일 제약 (확정값) ----
    max_audio_bytes: int = 50 * 1024 * 1024  # 50 MiB
    max_audio_seconds: int = 60 * 60  # 60분
    allowed_audio_extensions: tuple[str, ...] = (
        ".wav",
        ".mp3",
        ".m4a",
        ".mp4",
        ".ogg",
        ".oga",
        ".flac",
        ".webm",
    )
    allowed_audio_mime_types: tuple[str, ...] = (
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/mpeg",
        "audio/mp3",
        "audio/mp4",
        "audio/m4a",
        "audio/x-m4a",
        "video/mp4",
        "audio/ogg",
        "application/ogg",
        "audio/flac",
        "audio/x-flac",
        "audio/webm",
        "video/webm",
        "application/octet-stream",  # 브라우저가 형식을 못 붙이는 경우 확장자로 판정
    )

    # 목록 응답 기본값
    default_limit: int = 20
    max_limit: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
