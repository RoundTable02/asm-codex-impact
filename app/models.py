"""SQLAlchemy 모델 (SPEC 14장 데이터 모델).

모든 datetime 컬럼은 **naive UTC** 로 저장하고 응답 직렬화 시 `Z` 표기로 변환한다.
(SQLite/PostgreSQL 양쪽에서 동일하게 동작시키기 위한 선택)
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base
from app.enums import ActionStatus, ConsultationStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    consultations: Mapped[list["Consultation"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    actions: Mapped[list["ActionItem"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )


class Consultation(Base):
    __tablename__ = "consultations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consulted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=ConsultationStatus.UPLOADED.value, nullable=False, index=True
    )
    failure_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    client: Mapped[Client] = relationship(back_populates="consultations")
    analysis: Mapped["Analysis | None"] = relationship(
        back_populates="consultation", cascade="all, delete-orphan", uselist=False
    )
    risk_flags: Mapped[list["RiskFlag"]] = relationship(
        back_populates="consultation", cascade="all, delete-orphan"
    )
    action_items: Mapped[list["ActionItem"]] = relationship(
        back_populates="consultation", cascade="all, delete-orphan"
    )


Index("ix_consultations_client_consulted", Consultation.client_id, Consultation.consulted_at)


class Analysis(Base):
    """상담일지(초안/확정) + 후속 분석 결과를 함께 보관한다."""

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # --- 상담일지 (counseling_note) ---
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    main_contents: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    client_status: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    counseling_note_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # --- 후속 분석 결과 (상담일지 확정 이후에만 채운다) ---
    # {"compared_consultation_ids": [...], "important_changes": [...], "unresolved_issues": [...]}
    analysis_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    analysis_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    consultation: Mapped[Consultation] = relationship(back_populates="analysis")


class RiskFlag(Base):
    __tablename__ = "risk_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    consultation: Mapped[Consultation] = relationship(back_populates="risk_flags")


class ActionItem(Base):
    __tablename__ = "action_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default=ActionStatus.TODO.value, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    client: Mapped[Client] = relationship(back_populates="actions")
    consultation: Mapped[Consultation] = relationship(back_populates="action_items")
