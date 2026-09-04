from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .core import STATUS_KEYS

NonEmpty = Annotated[str, Field(min_length=1)]


def strip(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("빈 문자열은 허용되지 않습니다.")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClientCreate(StrictModel):
    name: Annotated[str, Field(max_length=100)]
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    gender: Literal["F", "M", "OTHER", "UNKNOWN"] | None = None
    memo: str | None = Field(default=None, max_length=2000)

    _strip_name = field_validator("name")(strip)

    @field_validator("birth_year")
    @classmethod
    def valid_birth_year(cls, value: int | None) -> int | None:
        if value is not None and value > datetime.now(UTC).year:
            raise ValueError("출생연도는 현재 연도 이하여야 합니다.")
        return value

    @field_validator("memo")
    @classmethod
    def strip_memo(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value


class TranscriptUpdate(StrictModel):
    transcript: Annotated[str, Field(max_length=200000)]
    _strip_transcript = field_validator("transcript")(strip)


class ClientStatus(StrictModel):
    health: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(max_length=100)
    nutrition: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(max_length=100)
    emotion: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(max_length=100)
    family: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(max_length=100)
    housing: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(max_length=100)
    social: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(max_length=100)

    @field_validator(*STATUS_KEYS)
    @classmethod
    def strip_items(cls, values: list[str]) -> list[str]:
        return [strip(value) for value in values]


class NoteUpdate(StrictModel):
    summary: Annotated[str, Field(max_length=5000)] | None = None
    main_contents: list[Annotated[str, Field(min_length=1, max_length=2000)]] | None = Field(
        default=None, max_length=100
    )
    client_status: ClientStatus | None = None

    @model_validator(mode="after")
    def requires_field(self):
        if not self.model_fields_set:
            raise ValueError("수정할 필드가 필요합니다.")
        if self.summary is not None:
            self.summary = strip(self.summary)
        if self.main_contents is not None:
            self.main_contents = [strip(item) for item in self.main_contents]
        return self


class ActionUpdate(StrictModel):
    status: Literal["TODO", "DONE", "DISMISSED"]


class CaseReportRequest(StrictModel):
    consultation_limit: int = Field(default=10, ge=3, le=10)


class JobResponse(BaseModel):
    consultation_id: int
    status: str
    status_url: str


class UploadForm(BaseModel):
    consulted_at: datetime
