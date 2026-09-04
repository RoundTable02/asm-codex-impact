import asyncio
import struct
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from app.main import create_app


def wav_bytes() -> bytes:
    return (
        b"RIFF"
        + struct.pack("<I", 36)
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 8000, 1, 8)
        + b"data"
        + struct.pack("<I", 0)
    )


async def wait_for(client: AsyncClient, consultation_id: int, target: str):
    for _ in range(30):
        response = await client.get(f"/consultations/{consultation_id}")
        if response.json()["status"] == target:
            return response.json()
        await asyncio.sleep(0.05)
    raise AssertionError("job did not finish")


async def test_fake_provider_runs_review_then_analysis_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("AI_MODE", "fake")
    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            client_id = (await client.post("/clients", json={"name": "김OO"})).json()["id"]
            upload = await client.post(
                f"/clients/{client_id}/consultations",
                data={"consulted_at": datetime.now(UTC).isoformat()},
                files={"audio": ("sample.wav", wav_bytes(), "audio/wav")},
            )
            assert upload.status_code == 202
            consultation_id = upload.json()["consultation_id"]
            await wait_for(client, consultation_id, "AWAITING_TRANSCRIPT_REVIEW")
            assert (
                await client.patch(
                    f"/consultations/{consultation_id}/transcript",
                    json={"transcript": "식사 준비가 어렵습니다."},
                )
            ).status_code == 200
            assert (
                await client.post(f"/consultations/{consultation_id}/transcript/confirm")
            ).status_code == 202
            await wait_for(client, consultation_id, "AWAITING_NOTE_REVIEW")
            note = await client.get(f"/consultations/{consultation_id}/counseling-note")
            assert note.status_code == 200
            assert (
                await client.patch(
                    f"/consultations/{consultation_id}/counseling-note",
                    json={"summary": "최종 상담일지"},
                )
            ).status_code == 200
            assert (
                await client.post(f"/consultations/{consultation_id}/counseling-note/confirm")
            ).status_code == 202
            await wait_for(client, consultation_id, "DONE")
            analysis = await client.get(f"/consultations/{consultation_id}/analysis")
            assert analysis.status_code == 200
            assert analysis.json()["summary"] == "최종 상담일지"


async def test_errors_follow_the_api_error_envelope(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("AI_MODE", "fake")
    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/consultations/999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
