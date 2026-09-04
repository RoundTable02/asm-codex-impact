"""응답 직렬화 (API_SPEC 3장 공통 데이터 구조).

datetime 은 모두 UTC `Z` 표기, date 는 `YYYY-MM-DD`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.enums import CLIENT_STATUS_KEYS
from app.models import ActionItem, Analysis, Client, Consultation, RiskFlag


def dt(value: datetime | None) -> str | None:
    """naive UTC datetime -> '2026-09-04T01:00:00Z'."""
    if value is None:
        return None
    return value.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def d(value: date | None) -> str | None:
    return value.isoformat() if value else None


def empty_client_status() -> dict[str, list[str]]:
    return {key: [] for key in CLIENT_STATUS_KEYS}


def normalize_client_status(raw: dict | None) -> dict[str, list[str]]:
    """6개 키를 항상 포함하도록 정규화한다."""
    out = empty_client_status()
    if not raw:
        return out
    for key in CLIENT_STATUS_KEYS:
        value = raw.get(key) or []
        out[key] = [str(item) for item in value]
    return out


def client_out(client: Client) -> dict[str, Any]:
    return {
        "id": client.id,
        "name": client.name,
        "birth_year": client.birth_year,
        "gender": client.gender,
        "memo": client.memo,
        "created_at": dt(client.created_at),
    }


def client_summary_out(
    client: Client,
    last_consulted_at: datetime | None,
    pending_action_count: int,
    has_important_risk: bool,
) -> dict[str, Any]:
    data = client_out(client)
    data.update(
        {
            "last_consulted_at": dt(last_consulted_at),
            "pending_action_count": pending_action_count,
            "has_important_risk": has_important_risk,
        }
    )
    return data


def failure_out(consultation: Consultation) -> dict[str, Any] | None:
    if not consultation.failure_code:
        return None
    return {
        "stage": consultation.failure_stage,
        "code": consultation.failure_code,
        "message": consultation.failure_message,
    }


def consultation_out(consultation: Consultation) -> dict[str, Any]:
    analysis = consultation.analysis
    return {
        "id": consultation.id,
        "client_id": consultation.client_id,
        "consulted_at": dt(consultation.consulted_at),
        "transcript": consultation.transcript,
        "transcript_confirmed_at": dt(consultation.transcript_confirmed_at),
        "counseling_note_confirmed_at": dt(
            analysis.counseling_note_confirmed_at if analysis else None
        ),
        "status": consultation.status,
        "failure": failure_out(consultation),
        "created_at": dt(consultation.created_at),
    }


def consultation_summary_out(consultation: Consultation) -> dict[str, Any]:
    analysis = consultation.analysis
    return {
        "id": consultation.id,
        "client_id": consultation.client_id,
        "consulted_at": dt(consultation.consulted_at),
        "created_at": dt(consultation.created_at),
        "status": consultation.status,
        "summary": analysis.summary if analysis else None,
        "counseling_note_confirmed_at": dt(
            analysis.counseling_note_confirmed_at if analysis else None
        ),
    }


def counseling_note_out(analysis: Analysis) -> dict[str, Any]:
    return {
        "consultation_id": analysis.consultation_id,
        "summary": analysis.summary,
        "main_contents": list(analysis.main_contents or []),
        "client_status": normalize_client_status(analysis.client_status),
        "confirmed_at": dt(analysis.counseling_note_confirmed_at),
        "created_at": dt(analysis.created_at),
    }


def risk_flag_out(risk: RiskFlag) -> dict[str, Any]:
    return {
        "id": risk.id,
        "consultation_id": risk.consultation_id,
        "type": risk.type,
        "severity": risk.severity,
        "description": risk.description,
        "evidence": risk.evidence,
        "resolved": risk.resolved,
        "created_at": dt(risk.created_at),
    }


def action_out(action: ActionItem) -> dict[str, Any]:
    return {
        "id": action.id,
        "client_id": action.client_id,
        "consultation_id": action.consultation_id,
        "action_type": action.action_type,
        "title": action.title,
        "description": action.description,
        "priority": action.priority,
        "reason": action.reason,
        "due_date": d(action.due_date),
        "status": action.status,
        "created_at": action.created_at and dt(action.created_at),
    }


def analysis_out(
    analysis: Analysis,
    risks: list[RiskFlag],
    actions: list[ActionItem],
) -> dict[str, Any]:
    payload = analysis.analysis_json or {}
    return {
        "consultation_id": analysis.consultation_id,
        "summary": analysis.summary,
        "client_status": normalize_client_status(analysis.client_status),
        "compared_consultation_ids": list(payload.get("compared_consultation_ids", [])),
        "important_changes": list(payload.get("important_changes", [])),
        "risk_flags": [risk_flag_out(r) for r in risks],
        "unresolved_issues": list(payload.get("unresolved_issues", [])),
        "recommended_actions": [action_out(a) for a in actions],
        "created_at": dt(analysis.analysis_created_at or analysis.created_at),
    }


def list_out(items: list[Any], total: int, limit: int, offset: int) -> dict[str, Any]:
    return {"items": items, "total": total, "limit": limit, "offset": offset}
