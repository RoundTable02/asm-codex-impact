"""명세에 정의된 enum 값 모음."""

from __future__ import annotations

from enum import Enum


class ConsultationStatus(str, Enum):
    UPLOADED = "UPLOADED"
    TRANSCRIBING = "TRANSCRIBING"
    AWAITING_TRANSCRIPT_REVIEW = "AWAITING_TRANSCRIPT_REVIEW"
    GENERATING_NOTE = "GENERATING_NOTE"
    AWAITING_NOTE_REVIEW = "AWAITING_NOTE_REVIEW"
    ANALYZING = "ANALYZING"
    DONE = "DONE"
    FAILED = "FAILED"


class FailureStage(str, Enum):
    UPLOADED = "UPLOADED"
    TRANSCRIBING = "TRANSCRIBING"
    GENERATING_NOTE = "GENERATING_NOTE"
    ANALYZING = "ANALYZING"


class FailureCode(str, Enum):
    UPLOAD_PROCESSING_FAILED = "UPLOAD_PROCESSING_FAILED"
    STT_FAILED = "STT_FAILED"
    NOTE_GENERATION_FAILED = "NOTE_GENERATION_FAILED"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"


STAGE_TO_FAILURE_CODE = {
    FailureStage.UPLOADED: FailureCode.UPLOAD_PROCESSING_FAILED,
    FailureStage.TRANSCRIBING: FailureCode.STT_FAILED,
    FailureStage.GENERATING_NOTE: FailureCode.NOTE_GENERATION_FAILED,
    FailureStage.ANALYZING: FailureCode.ANALYSIS_FAILED,
}

FAILURE_MESSAGES = {
    FailureCode.UPLOAD_PROCESSING_FAILED: "녹음 파일을 처리하지 못했습니다.",
    FailureCode.STT_FAILED: "녹음 파일을 전사하지 못했습니다.",
    FailureCode.NOTE_GENERATION_FAILED: "상담일지를 생성하지 못했습니다.",
    FailureCode.ANALYSIS_FAILED: "후속 분석을 완료하지 못했습니다.",
}


class Gender(str, Enum):
    F = "F"
    M = "M"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class StatusCategory(str, Enum):
    """client_status / important_changes 의 category (대문자)."""

    HEALTH = "HEALTH"
    NUTRITION = "NUTRITION"
    EMOTION = "EMOTION"
    FAMILY = "FAMILY"
    HOUSING = "HOUSING"
    SOCIAL = "SOCIAL"


CLIENT_STATUS_KEYS: tuple[str, ...] = (
    "health",
    "nutrition",
    "emotion",
    "family",
    "housing",
    "social",
)


class ChangeDirection(str, Enum):
    IMPROVED = "IMPROVED"
    UNCHANGED = "UNCHANGED"
    WORSENED = "WORSENED"
    UNKNOWN = "UNKNOWN"


class RiskType(str, Enum):
    HEALTH = "HEALTH"
    NUTRITION = "NUTRITION"
    EMOTION = "EMOTION"
    ISOLATION = "ISOLATION"
    ABUSE = "ABUSE"
    HOUSING = "HOUSING"
    ECONOMIC = "ECONOMIC"
    SAFETY = "SAFETY"
    OTHER = "OTHER"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ActionType(str, Enum):
    FOLLOW_UP_CALL = "FOLLOW_UP_CALL"
    HOME_VISIT = "HOME_VISIT"
    CONTACT_FAMILY = "CONTACT_FAMILY"
    CONTACT_SUPPORT_WORKER = "CONTACT_SUPPORT_WORKER"
    RESOURCE_REFERRAL = "RESOURCE_REFERRAL"
    CASE_REVIEW = "CASE_REVIEW"
    CHECK_HEALTH = "CHECK_HEALTH"
    CHECK_NUTRITION = "CHECK_NUTRITION"
    OTHER = "OTHER"


class Priority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ActionStatus(str, Enum):
    TODO = "TODO"
    DONE = "DONE"
    DISMISSED = "DISMISSED"
