import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.ai import AIServiceError
from app.core import Settings, empty_status, now
from app.db import Base, create_database
from app.main import execute_job
from app.models import ActionItem, Analysis, Client, Consultation, ProcessingJob, RiskFlag
from app.recover_jobs import recover


@pytest.fixture
async def pending_analysis(tmp_path):
    engine, factory = create_database(f"sqlite+aiosqlite:///{tmp_path}/jobs.db")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        client = Client(name="합성 테스트")
        session.add(client)
        await session.flush()
        consultation = Consultation(
            client_id=client.id,
            consulted_at=now(),
            status="ANALYZING",
            transcript="합성 전사문",
            transcript_confirmed_at=now(),
            counseling_note_confirmed_at=now(),
        )
        session.add(consultation)
        await session.flush()
        session.add(
            Analysis(
                consultation_id=consultation.id,
                counseling_note={
                    "summary": "상담자가 확정한 내용",
                    "main_contents": [],
                    "client_status": empty_status(),
                },
            )
        )
        job = ProcessingJob(consultation_id=consultation.id, stage="ANALYZING", state="RUNNING")
        session.add(job)
        await session.commit()
        job_id, consultation_id = job.id, consultation.id
    app = SimpleNamespace(
        state=SimpleNamespace(
            session_factory=factory,
            ai=SimpleNamespace(analysis=AsyncMock()),
            settings=Settings(ai_mode="fake"),
        )
    )
    yield app, job_id, consultation_id
    await engine.dispose()


async def assert_failed_without_partial_results(app, job_id, consultation_id):
    async with app.state.session_factory() as session:
        consultation = await session.get(Consultation, consultation_id)
        assert consultation.status == "FAILED"
        assert consultation.failure["code"] == "ANALYSIS_FAILED"
        assert consultation.transcript == "합성 전사문"
        assert consultation.counseling_note_confirmed_at is not None
        record = await session.get(Analysis, consultation_id)
        assert record.counseling_note["summary"] == "상담자가 확정한 내용"
        assert record.analysis_json is None
        assert (await session.get(ProcessingJob, job_id)).state == "FAILED"
        assert await session.scalar(select(func.count()).select_from(RiskFlag)) == 0
        assert await session.scalar(select(func.count()).select_from(ActionItem)) == 0


async def test_string_actions_do_not_leave_analysis_running(pending_analysis):
    app, job_id, consultation_id = pending_analysis
    app.state.ai.analysis.return_value = {
        "important_changes": [],
        "risk_flags": [],
        "unresolved_issues": [],
        "recommended_actions": ["안부 전화하기"],
    }
    await execute_job(app, job_id)
    await assert_failed_without_partial_results(app, job_id, consultation_id)


async def test_provider_failure_survives_rollback(pending_analysis):
    app, job_id, consultation_id = pending_analysis
    app.state.ai.analysis.side_effect = AIServiceError("private provider detail")
    await execute_job(app, job_id)
    await assert_failed_without_partial_results(app, job_id, consultation_id)


async def test_unexpected_failure_is_logged_without_sensitive_message(pending_analysis, caplog):
    app, job_id, consultation_id = pending_analysis
    app.state.ai.analysis.side_effect = RuntimeError("private provider detail")
    await execute_job(app, job_id)
    await assert_failed_without_partial_results(app, job_id, consultation_id)
    assert "RuntimeError" in caplog.text
    assert "private provider detail" not in caplog.text


async def test_analysis_timeout_is_terminal(pending_analysis):
    app, job_id, consultation_id = pending_analysis
    # Settings are injected to avoid waiting for the production deadline in a test.
    app.state.settings = SimpleNamespace(job_timeout_seconds=0.01)

    async def stalled(*args):
        await asyncio.Event().wait()

    app.state.ai.analysis.side_effect = stalled
    await asyncio.wait_for(execute_job(app, job_id), timeout=1)
    await assert_failed_without_partial_results(app, job_id, consultation_id)


async def test_recovery_preview_preserves_data_and_apply_is_idempotent(pending_analysis):
    app, job_id, consultation_id = pending_analysis
    factory = app.state.session_factory
    assert "eligible" in await recover(factory, consultation_id)
    async with factory() as session:
        assert (await session.get(ProcessingJob, job_id)).state == "RUNNING"
    assert "requeued" in await recover(factory, consultation_id, apply=True)
    assert "already_queued" in await recover(factory, consultation_id, apply=True)
    async with factory() as session:
        record = await session.get(Analysis, consultation_id)
        assert record.counseling_note["summary"] == "상담자가 확정한 내용"
        consultation = await session.get(Consultation, consultation_id)
        assert consultation.counseling_note_confirmed_at is not None


async def test_recovery_refuses_completed_and_failed_records(pending_analysis):
    app, job_id, consultation_id = pending_analysis
    for status in ("DONE", "FAILED"):
        async with app.state.session_factory() as session:
            consultation = await session.get(Consultation, consultation_id)
            consultation.status = status
            await session.commit()
        with pytest.raises(ValueError, match="Only stalled"):
            await recover(app.state.session_factory, consultation_id, apply=True)


async def test_recovery_refuses_a_job_owned_by_the_updated_worker(pending_analysis):
    app, job_id, consultation_id = pending_analysis
    async with app.state.session_factory() as session:
        job = await session.get(ProcessingJob, job_id)
        job.payload = {"worker_version": 1}
        await session.commit()
    with pytest.raises(ValueError, match="updated worker owns"):
        await recover(app.state.session_factory, consultation_id, apply=True)


async def test_database_commit_error_rolls_back_all_results(pending_analysis, monkeypatch):
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.ext.asyncio import AsyncSession

    app, job_id, consultation_id = pending_analysis
    app.state.ai.analysis.return_value = {
        "important_changes": [],
        "unresolved_issues": [],
        "recommended_actions": [],
        "risk_flags": [
            {"type": "HEALTH", "severity": "LOW", "description": "확인 필요", "evidence": None}
        ],
    }
    original_commit = AsyncSession.commit
    failed_once = False

    async def broken_commit(session):
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            await session.flush()
            raise OperationalError("statement containing sensitive data", {}, Exception("private"))
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", broken_commit)
    await execute_job(app, job_id)
    await assert_failed_without_partial_results(app, job_id, consultation_id)


async def test_valid_actions_are_saved_with_korean_due_date(pending_analysis):
    from datetime import UTC, datetime

    app, job_id, consultation_id = pending_analysis
    async with app.state.session_factory() as session:
        consultation = await session.get(Consultation, consultation_id)
        consultation.consulted_at = datetime(2026, 9, 4, 16, tzinfo=UTC)
        await session.commit()
    app.state.ai.analysis.return_value = {
        "important_changes": [],
        "unresolved_issues": [],
        "risk_flags": [
            {
                "type": "HEALTH",
                "severity": "LOW",
                "description": "확인 필요",
                "evidence": "존재하지 않는 인용",
            }
        ],
        "recommended_actions": [
            {
                "action_type": "FOLLOW_UP_CALL",
                "title": "합성 테스트 전화",
                "description": None,
                "priority": "LOW",
                "reason": "확인 필요",
                "due_in_days": 1,
            }
        ],
    }
    await execute_job(app, job_id)
    async with app.state.session_factory() as session:
        assert (await session.get(Consultation, consultation_id)).status == "DONE"
        action = await session.scalar(select(ActionItem))
        assert action.due_date.isoformat() == "2026-09-06"
        assert (await session.scalar(select(RiskFlag))).evidence is None
        assert (await session.get(ProcessingJob, job_id)).state == "DONE"
