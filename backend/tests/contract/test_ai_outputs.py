import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.ai import AIService, AIServiceError
from app.ai_schemas import FollowUpOutput
from app.core import Settings, empty_status


def service_with_response(output, status="completed"):
    service = AIService(Settings(ai_mode="fake"))
    service.settings.ai_mode = "openai"
    service.client = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(status=status, output_text=json.dumps(output)),
            )
        )
    )
    return service


async def test_analysis_requests_structured_output_and_validates_it():
    output = {
        "important_changes": [],
        "risk_flags": [],
        "unresolved_issues": [],
        "recommended_actions": [],
    }
    service = service_with_response(output)
    assert await service.analysis({"summary": "확정본"}, "합성 전사문", []) == output
    params = service.client.responses.create.call_args.kwargs
    assert params["text"]["format"]["type"] == "json_schema"
    assert params["text"]["format"]["strict"] is True
    assert params["text"]["format"]["schema"] == FollowUpOutput.model_json_schema()
    assert params["store"] is False


@pytest.mark.parametrize(
    "output,status",
    [
        (
            {
                "important_changes": [],
                "risk_flags": [],
                "unresolved_issues": [],
                "recommended_actions": ["Call the client"],
            },
            "completed",
        ),
        ({}, "incomplete"),
        ({}, "completed"),
    ],
)
async def test_invalid_provider_output_is_rejected(output, status):
    service = service_with_response(output, status)
    with pytest.raises(AIServiceError):
        await service.analysis({}, "test", [])


async def test_note_schema_rejects_wrong_status_values():
    service = service_with_response(
        {
            "summary": "합성",
            "main_contents": [],
            "client_status": empty_status() | {"health": "잘못된 형식"},
        }
    )
    with pytest.raises(AIServiceError):
        await service.note("합성 전사문")
