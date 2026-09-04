"""API_SPEC 11장 공통 오류 응답."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class ApiError(HTTPException):
    """{"error": {...}} 형태로 직렬화되는 도메인 오류."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
        current_status: str | None = None,
        allowed_statuses: list[str] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "code": code,
            "message": message,
            "details": details or [],
        }
        if current_status is not None:
            payload["current_status"] = current_status
        if allowed_statuses is not None:
            payload["allowed_statuses"] = allowed_statuses
        super().__init__(status_code=status_code, detail={"error": payload})


def validation_error(details: list[dict[str, Any]] | None = None, message: str = "요청 값을 확인해주세요.") -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message, details)


def not_found(message: str) -> ApiError:
    return ApiError(404, "NOT_FOUND", message)


def invalid_state(message: str, current: str, allowed: list[str]) -> ApiError:
    return ApiError(409, "INVALID_STATE", message, current_status=current, allowed_statuses=allowed)


def result_not_ready(message: str, current: str | None = None) -> ApiError:
    return ApiError(409, "RESULT_NOT_READY", message, current_status=current)


def processing_failed(message: str, current: str | None = None) -> ApiError:
    return ApiError(409, "PROCESSING_FAILED", message, current_status=current)


def insufficient_data(message: str) -> ApiError:
    return ApiError(409, "INSUFFICIENT_DATA", message)


def file_too_large(message: str) -> ApiError:
    return ApiError(413, "FILE_TOO_LARGE", message)


def unsupported_audio_format(message: str) -> ApiError:
    return ApiError(415, "UNSUPPORTED_AUDIO_FORMAT", message)


def invalid_audio(message: str, details: list[dict[str, Any]] | None = None) -> ApiError:
    return ApiError(422, "INVALID_AUDIO", message, details)


def service_unavailable(message: str) -> ApiError:
    return ApiError(503, "SERVICE_UNAVAILABLE", message)


def ai_service_error(message: str) -> ApiError:
    return ApiError(502, "AI_SERVICE_ERROR", message)


def ai_timeout(message: str) -> ApiError:
    return ApiError(504, "AI_TIMEOUT", message)
