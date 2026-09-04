from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from fastapi import HTTPException
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConsultationStatus(StrEnum):
    UPLOADED = "UPLOADED"
    TRANSCRIBING = "TRANSCRIBING"
    AWAITING_TRANSCRIPT_REVIEW = "AWAITING_TRANSCRIPT_REVIEW"
    GENERATING_NOTE = "GENERATING_NOTE"
    AWAITING_NOTE_REVIEW = "AWAITING_NOTE_REVIEW"
    ANALYZING = "ANALYZING"
    DONE = "DONE"
    FAILED = "FAILED"


STATUS_KEYS = ("health", "nutrition", "emotion", "family", "housing", "social")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite+aiosqlite:///./social_worker_ax.db"
    ai_mode: str = "openai"
    openai_api_key: str | None = None
    openai_stt_model: str = "gpt-4o-mini-transcribe"
    openai_llm_model: str = "gpt-4.1-mini"
    # Hackathon demo default. Restrict this to the frontend origin before any real-data launch.
    cors_origins: str = "*"
    max_audio_bytes: int = 25 * 1024 * 1024
    job_poll_seconds: float = 0.2
    case_report_timeout_seconds: int = 30


def now() -> datetime:
    return datetime.now(UTC)


def api_error(status: int, code: str, message: str, **extra: object) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


def empty_status() -> dict[str, list[str]]:
    return {key: [] for key in STATUS_KEYS}
