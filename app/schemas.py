"""요청 본문 검증 스키마.

응답은 `app/serializers.py` 에서 dict 로 직접 조립한다.
(UTC `Z` 표기, 필드 생략 규칙 등을 명세대로 통제하기 위함)
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.enums import CLIENT_STATUS_KEYS, ActionStatus, Gender


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _clean(value: str) -> str:
    return value.strip()


class ClientCreate(StrictModel):
    name: str = Field(min_length=1)
    birth_year: int | None = None
    gender: Gender | None = None
    memo: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = _clean(v)
        if not 1 <= len(v) <= 100:
            raise ValueError("이름은 1~100자여야 합니다.")
        return v

    @field_validator("birth_year")
    @classmethod
    def _birth_year(cls, v: int | None) -> int | None:
        if v is None:
            return None
        current_year = datetime.now().year
        if not 1900 <= v <= current_year:
            raise ValueError(f"출생연도는 1900~{current_year} 사이여야 합니다.")
        return v

    @field_validator("memo")
    @classmethod
    def _memo(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = _clean(v)
        if len(v) > 2000:
            raise ValueError("메모는 최대 2,000자입니다.")
        return v


class TranscriptPatch(StrictModel):
    transcript: str

    @field_validator("transcript")
    @classmethod
    def _transcript(cls, v: str) -> str:
        v = _clean(v)
        if not v:
            raise ValueError("전사문은 비어 있을 수 없습니다.")
        if len(v) > 200_000:
            raise ValueError("전사문은 최대 200,000자입니다.")
        return v


class ClientStatusIn(StrictModel):
    health: list[str]
    nutrition: list[str]
    emotion: list[str]
    family: list[str]
    housing: list[str]
    social: list[str]

    @model_validator(mode="after")
    def _validate_items(self) -> "ClientStatusIn":
        for key in CLIENT_STATUS_KEYS:
            items = getattr(self, key)
            if len(items) > 100:
                raise ValueError(f"client_status.{key} 항목은 최대 100개입니다.")
            cleaned = []
            for item in items:
                s = _clean(item)
                if not 1 <= len(s) <= 2000:
                    raise ValueError(f"client_status.{key} 항목은 1~2,000자여야 합니다.")
                cleaned.append(s)
            setattr(self, key, cleaned)
        return self


class CounselingNotePatch(StrictModel):
    summary: str | None = None
    main_contents: list[str] | None = None
    client_status: ClientStatusIn | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_explicit_null(cls, data):
        if isinstance(data, dict):
            for key, value in data.items():
                if value is None:
                    raise ValueError(f"{key} 에는 null 을 허용하지 않습니다.")
        return data

    @field_validator("summary")
    @classmethod
    def _summary(cls, v: str | None) -> str | None:
        if v is None:
            raise ValueError("summary 에는 null 을 허용하지 않습니다.")
        v = _clean(v)
        if not 1 <= len(v) <= 5000:
            raise ValueError("상담 요약은 1~5,000자여야 합니다.")
        return v

    @field_validator("main_contents")
    @classmethod
    def _main_contents(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            raise ValueError("main_contents 에는 null 을 허용하지 않습니다.")
        if len(v) > 100:
            raise ValueError("main_contents 는 최대 100개입니다.")
        cleaned = []
        for item in v:
            s = _clean(item)
            if not 1 <= len(s) <= 2000:
                raise ValueError("main_contents 항목은 1~2,000자여야 합니다.")
            cleaned.append(s)
        return cleaned

    @model_validator(mode="after")
    def _at_least_one(self) -> "CounselingNotePatch":
        if self.summary is None and self.main_contents is None and self.client_status is None:
            raise ValueError("summary, main_contents, client_status 중 하나 이상이 필요합니다.")
        return self


class ActionPatch(StrictModel):
    status: ActionStatus


class CaseReportRequest(StrictModel):
    consultation_limit: int = Field(default=10, ge=3, le=10)
