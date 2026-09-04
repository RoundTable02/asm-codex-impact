"""STT / LLM 어댑터 인터페이스.

SPEC 16장 AI 처리 원칙을 프롬프트/규칙 계층에서 강제한다.
구현체는 `mock.py`(기본)와 `openai_provider.py`(실연동) 두 가지다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


class AIServiceError(RuntimeError):
    """외부 AI 서비스 오류."""


class AITimeoutError(RuntimeError):
    """외부 AI 서비스 제한 시간 초과."""


@dataclass
class NoteDraft:
    """상담일지 초안 (위험신호·Action 은 포함하지 않는다)."""

    summary: str
    main_contents: list[str]
    client_status: dict[str, list[str]]


@dataclass
class RiskDraft:
    type: str
    severity: str
    description: str
    evidence: str | None = None


@dataclass
class ActionDraft:
    action_type: str
    title: str
    priority: str
    reason: str
    description: str | None = None
    due_in_days: int | None = None


@dataclass
class ChangeDraft:
    category: str
    change: str
    previous: str | None
    current: str | None
    description: str


@dataclass
class AnalysisDraft:
    important_changes: list[ChangeDraft] = field(default_factory=list)
    risk_flags: list[RiskDraft] = field(default_factory=list)
    unresolved_issues: list[str] = field(default_factory=list)
    recommended_actions: list[ActionDraft] = field(default_factory=list)


@dataclass
class PriorConsultation:
    """후속 분석 비교 대상 (확정된 DONE 상담)."""

    consultation_id: int
    consulted_at: datetime
    summary: str
    client_status: dict[str, list[str]]


@dataclass
class ClientProfile:
    id: int
    name: str
    birth_year: int | None
    gender: str | None
    memo: str | None


@dataclass
class TimelineEntry:
    consultation_id: int
    consulted_at: datetime
    description: str


@dataclass
class CaseReportDraft:
    client_overview: str
    recent_status: dict[str, list[str]]
    timeline: list[TimelineEntry]
    current_risks: list[str]
    support_status: list[str]
    unresolved_issues: list[str]
    discussion_points: list[str]


class AIProvider(Protocol):
    def transcribe(self, audio_bytes: bytes, filename: str, content_type: str | None) -> str:
        """녹음 파일을 전사문으로 변환한다."""

    def generate_note(self, transcript: str, client: ClientProfile) -> NoteDraft:
        """확정 전사문으로 상담일지 초안을 생성한다."""

    def analyze(
        self,
        note: NoteDraft,
        transcript: str,
        client: ClientProfile,
        priors: list[PriorConsultation],
    ) -> AnalysisDraft:
        """확정 상담일지 기준으로 상태변화·위험신호·미해결 이슈·추천 Action 을 생성한다."""

    def generate_case_report(
        self,
        client: ClientProfile,
        priors: list[PriorConsultation],
        open_risks: list[RiskDraft],
        open_actions: list[ActionDraft],
        unresolved_issues: list[str],
    ) -> CaseReportDraft:
        """사례회의용 종합 리포트를 생성한다(동기)."""
