from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .ai import AIService, AIServiceError
from .ai_schemas import FollowUpOutput, NoteOutput
from .core import ConsultationStatus, Settings, api_error, now
from .db import Base, create_database
from .models import ActionItem, Analysis, Client, Consultation, ProcessingJob, RiskFlag
from .schemas import ActionUpdate, CaseReportRequest, ClientCreate, NoteUpdate, TranscriptUpdate

logger = logging.getLogger("uvicorn.error")


def utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def client_json(client: Client) -> dict[str, Any]:
    return {
        "id": client.id,
        "name": client.name,
        "birth_year": client.birth_year,
        "gender": client.gender,
        "memo": client.memo,
        "created_at": utc(client.created_at),
    }


def consultation_json(item: Consultation) -> dict[str, Any]:
    return {
        "id": item.id,
        "client_id": item.client_id,
        "consulted_at": utc(item.consulted_at),
        "transcript": item.transcript,
        "transcript_confirmed_at": utc(item.transcript_confirmed_at)
        if item.transcript_confirmed_at
        else None,
        "counseling_note_confirmed_at": utc(item.counseling_note_confirmed_at)
        if item.counseling_note_confirmed_at
        else None,
        "status": item.status,
        "failure": item.failure,
        "created_at": utc(item.created_at),
    }


def action_json(item: ActionItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "client_id": item.client_id,
        "consultation_id": item.consultation_id,
        "action_type": item.action_type,
        "title": item.title,
        "description": item.description,
        "priority": item.priority,
        "reason": item.reason,
        "due_date": item.due_date.isoformat() if item.due_date else None,
        "status": item.status,
        "created_at": utc(item.created_at),
    }


def risk_json(item: RiskFlag) -> dict[str, Any]:
    return {
        "id": item.id,
        "consultation_id": item.consultation_id,
        "type": item.type,
        "severity": item.severity,
        "description": item.description,
        "evidence": item.evidence,
        "resolved": item.resolved,
        "created_at": utc(item.created_at),
    }


def note_json(analysis: Analysis, consultation: Consultation) -> dict[str, Any]:
    note = analysis.counseling_note
    return {
        "consultation_id": consultation.id,
        **note,
        "confirmed_at": utc(consultation.counseling_note_confirmed_at)
        if consultation.counseling_note_confirmed_at
        else None,
        "created_at": utc(analysis.created_at),
    }


async def required(session: AsyncSession, model: type, item_id: int, label: str):
    item = await session.get(model, item_id)
    if not item:
        raise api_error(404, "NOT_FOUND", f"{label}을 찾을 수 없습니다.")
    return item


async def require_state(
    session: AsyncSession, consultation_id: int, allowed: set[str]
) -> Consultation:
    item = await required(session, Consultation, consultation_id, "상담")
    if item.status not in allowed:
        raise api_error(
            409,
            "INVALID_STATE",
            "현재 상태에서는 요청을 수행할 수 없습니다.",
            current_status=item.status,
            allowed_statuses=sorted(allowed),
        )
    return item


def valid_audio(data: bytes, filename: str) -> bool:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a", ".mp4", ".ogg", ".webm"}:
        return False
    return (
        (suffix == ".wav" and data.startswith(b"RIFF") and data[8:12] == b"WAVE")
        or (suffix == ".mp3" and (data.startswith(b"ID3") or data.startswith(b"\xff\xfb")))
        or (suffix in {".m4a", ".mp4"} and b"ftyp" in data[:32])
        or (suffix == ".ogg" and data.startswith(b"OggS"))
        or (suffix == ".webm" and data.startswith(b"\x1aE\xdf\xa3"))
    )


async def job_loop(app: FastAPI) -> None:
    while True:
        try:
            async with app.state.session_factory() as session:
                job = (
                    await session.execute(
                        select(ProcessingJob)
                        .where(ProcessingJob.state == "QUEUED")
                        .order_by(ProcessingJob.id)
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if job:
                    job_id = job.id
                    claimed = await session.execute(
                        update(ProcessingJob)
                        .where(ProcessingJob.id == job_id, ProcessingJob.state == "QUEUED")
                        .values(
                            state="RUNNING",
                            payload={
                                **(job.payload or {}),
                                "worker_version": 1,
                                "started_at": now().isoformat(),
                            },
                        )
                    )
                    await session.commit()
                    if claimed.rowcount:
                        await execute_job(app, job_id)
                else:
                    await asyncio.sleep(app.state.settings.job_poll_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("job_loop_failed error_type=%s", type(exc).__name__)
            await asyncio.sleep(1)


async def fail_job(
    session: AsyncSession, consultation: Consultation, job: ProcessingJob, code: str
) -> None:
    consultation.status = ConsultationStatus.FAILED
    consultation.failure = {
        "stage": job.stage,
        "code": code,
        "message": "처리 중 오류가 발생했습니다.",
    }
    job.state = "FAILED"
    await session.commit()


async def execute_job(app: FastAPI, job_id: int) -> None:
    try:
        await asyncio.wait_for(
            execute_job_result(app, job_id), timeout=app.state.settings.job_timeout_seconds
        )
    except asyncio.CancelledError:
        # The result session is closed/rolled back before using a fresh failure session.
        await record_job_failure(app, job_id, "CancelledError")
        raise
    except Exception as exc:
        cause = f"/{type(exc.__cause__).__name__}" if exc.__cause__ else ""
        await record_job_failure(app, job_id, type(exc).__name__ + cause)


async def record_job_failure(app: FastAPI, job_id: int, error_type: str) -> None:
    # Never log exception messages/tracebacks: DB errors may contain consultation data.
    logger.error("job_failed job_id=%s error_type=%s", job_id, error_type)
    for attempt in range(3):
        try:
            async with asyncio.timeout(10):
                async with app.state.session_factory() as session:
                    job = await session.get(ProcessingJob, job_id)
                    if not job or job.state != "RUNNING":
                        return
                    consultation = await session.get(Consultation, job.consultation_id)
                    if not consultation or consultation.status in {"DONE", "FAILED"}:
                        return
                    code = {
                        "TRANSCRIBING": "STT_FAILED",
                        "GENERATING_NOTE": "NOTE_GENERATION_FAILED",
                        "ANALYZING": "ANALYSIS_FAILED",
                    }[job.stage]
                    await fail_job(session, consultation, job, code)
                    if job.stage == "TRANSCRIBING" and (job.payload or {}).get("path"):
                        with suppress(OSError):
                            Path((job.payload or {})["path"]).unlink(missing_ok=True)
                    return
        except Exception as exc:
            logger.error(
                "job_failure_save_failed job_id=%s attempt=%s error_type=%s",
                job_id,
                attempt + 1,
                type(exc).__name__,
            )
            if attempt < 2:
                await asyncio.sleep(0.2 * (attempt + 1))


async def execute_job_result(app: FastAPI, job_id: int) -> None:
    async with app.state.session_factory() as session:
        job = await session.get(ProcessingJob, job_id)
        if not job or job.state != "RUNNING":
            return
        consultation = await required(session, Consultation, job.consultation_id, "상담")
        try:
            if job.stage == "TRANSCRIBING":
                path = Path((job.payload or {})["path"])
                if not path.exists():
                    await fail_job(session, consultation, job, "STT_FAILED")
                    return
                consultation.status = ConsultationStatus.TRANSCRIBING
                await session.commit()
                transcript = await app.state.ai.transcribe(path.read_bytes(), path.name)
                consultation.transcript = transcript
                consultation.status = ConsultationStatus.AWAITING_TRANSCRIPT_REVIEW
                job.state = "DONE"
            elif job.stage == "GENERATING_NOTE":
                note = await app.state.ai.note(consultation.transcript or "")
                note = NoteOutput.model_validate(note).model_dump()
                session.add(
                    Analysis(
                        consultation_id=consultation.id, counseling_note=note, analysis_json=None
                    )
                )
                consultation.status = ConsultationStatus.AWAITING_NOTE_REVIEW
                job.state = "DONE"
            elif job.stage == "ANALYZING":
                record = await required(session, Analysis, consultation.id, "상담일지")
                prior = (
                    await session.execute(
                        select(Consultation, Analysis)
                        .join(Analysis, Analysis.consultation_id == Consultation.id)
                        .where(
                            and_(
                                Consultation.client_id == consultation.client_id,
                                Consultation.status == ConsultationStatus.DONE,
                                Consultation.consulted_at < consultation.consulted_at,
                            )
                        )
                        .order_by(Consultation.consulted_at.desc(), Consultation.id.desc())
                        .limit(5)
                    )
                ).all()
                previous = [
                    {
                        "id": c.id,
                        "summary": a.counseling_note["summary"],
                        "client_status": a.counseling_note["client_status"],
                    }
                    for c, a in prior
                ]
                result = await app.state.ai.analysis(
                    record.counseling_note, consultation.transcript or "", previous
                )
                result = FollowUpOutput.model_validate(result).model_dump()
                if not previous:
                    for change in result["important_changes"]:
                        change["change"] = "UNKNOWN"
                        change["previous"] = None
                risks = result.get("risk_flags", [])
                actions = result.get("recommended_actions", [])
                for risk in risks:
                    evidence = risk.get("evidence")
                    session.add(
                        RiskFlag(
                            consultation_id=consultation.id,
                            type=str(risk.get("type", "OTHER"))[:20],
                            severity=str(risk.get("severity", "LOW"))[:10],
                            description=str(risk.get("description", "확인 필요"))[:2000],
                            evidence=evidence
                            if isinstance(evidence, str)
                            and evidence in (consultation.transcript or "")
                            else None,
                        )
                    )
                for action in actions:
                    days = action.get("due_in_days")
                    due = None
                    if isinstance(days, int) and 0 <= days <= 365:
                        consulted_at = consultation.consulted_at
                        if consulted_at.tzinfo is None:
                            consulted_at = consulted_at.replace(tzinfo=UTC)
                        due = consulted_at.astimezone(ZoneInfo("Asia/Seoul")).date() + timedelta(
                            days=days
                        )
                    session.add(
                        ActionItem(
                            client_id=consultation.client_id,
                            consultation_id=consultation.id,
                            action_type=str(action.get("action_type", "OTHER"))[:32],
                            title=str(action.get("title", "확인 필요"))[:200],
                            description=action.get("description"),
                            priority=str(action.get("priority", "MEDIUM"))[:10],
                            reason=str(action.get("reason", "상담 내용 확인 필요"))[:2000],
                            due_date=due,
                        )
                    )
                record.analysis_json = {
                    "compared_consultation_ids": [c.id for c, _ in prior],
                    "important_changes": result.get("important_changes", []),
                    "unresolved_issues": result.get("unresolved_issues", []),
                }
                record.analyzed_at = now()
                consultation.status = ConsultationStatus.DONE
                job.state = "DONE"
            await session.commit()
            if job.stage == "TRANSCRIBING":
                with suppress(OSError):
                    path.unlink(missing_ok=True)
            logger.info("job_completed job_id=%s stage=%s", job_id, job.stage)
        except BaseException:
            await session.rollback()
            raise


def create_app() -> FastAPI:
    settings = Settings()
    engine, session_factory = create_database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.ai_mode not in {"fake", "openai"}:
            raise RuntimeError("AI_MODE must be either fake or openai")
        if settings.ai_mode == "openai" and not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when AI_MODE=openai")
        app.state.settings, app.state.session_factory, app.state.ai = (
            settings,
            session_factory,
            AIService(settings),
        )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        worker = asyncio.create_task(job_loop(app))
        try:
            yield
        finally:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
            await engine.dispose()

    app = FastAPI(title="Social Worker AX API", lifespan=lifespan)
    origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PATCH"],
            allow_headers=["Content-Type"],
            allow_credentials=False,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(map(str, error["loc"][1:])), "reason": error["msg"]}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "요청 값을 확인해주세요.",
                    "details": details,
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(_: Request, exc: HTTPException):
        detail = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": "HTTP_ERROR", "message": str(exc.detail)}
        )
        return JSONResponse(status_code=exc.status_code, content={"error": detail})

    @app.exception_handler(Exception)
    async def error_handler(_: Request, _exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "예상하지 못한 오류가 발생했습니다.",
                    "details": [],
                }
            },
        )

    @app.get("/health/live")
    async def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready():
        return {"status": "ready"}

    @app.post("/clients", status_code=201)
    async def create_client(body: ClientCreate):
        async with session_factory() as session:
            client = Client(**body.model_dump())
            session.add(client)
            await session.commit()
            await session.refresh(client)
            return JSONResponse(
                status_code=201,
                content=client_json(client),
                headers={"Location": f"/clients/{client.id}"},
            )

    @app.get("/clients")
    async def clients(search: str | None = None, limit: int = 20, offset: int = 0):
        if not 1 <= limit <= 100 or offset < 0:
            raise api_error(422, "VALIDATION_ERROR", "페이지 값을 확인해주세요.")
        async with session_factory() as session:
            query = select(Client)
            if search and search.strip():
                escaped_search = search.strip().replace("%", "\\%").replace("_", "\\_")
                query = query.where(Client.name.ilike(f"%{escaped_search}%", escape="\\"))
            total = (await session.scalar(select(func.count()).select_from(query.subquery()))) or 0
            items = (
                await session.scalars(
                    query.order_by(Client.created_at.desc(), Client.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return {
                "items": [
                    client_json(item)
                    | {
                        "last_consulted_at": None,
                        "pending_action_count": 0,
                        "has_important_risk": False,
                    }
                    for item in items
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    @app.get("/clients/{client_id}")
    async def client_detail(client_id: int):
        async with session_factory() as session:
            client = await required(session, Client, client_id, "내담자")
            recent = (
                await session.scalars(
                    select(Consultation)
                    .where(Consultation.client_id == client_id)
                    .order_by(Consultation.consulted_at.desc(), Consultation.id.desc())
                    .limit(5)
                )
            ).all()
            done = (
                await session.scalars(
                    select(Consultation)
                    .where(
                        and_(
                            Consultation.client_id == client_id,
                            Consultation.status == ConsultationStatus.DONE,
                        )
                    )
                    .order_by(Consultation.consulted_at.desc(), Consultation.id.desc())
                    .limit(1)
                )
            ).first()
            note = await session.get(Analysis, done.id) if done else None
            pending = (
                await session.scalars(
                    select(ActionItem)
                    .where(and_(ActionItem.client_id == client_id, ActionItem.status == "TODO"))
                    .order_by(ActionItem.due_date.asc().nulls_last(), ActionItem.id)
                    .limit(5)
                )
            ).all()
            return client_json(client) | {
                "last_consulted_at": utc(recent[0].consulted_at) if recent else None,
                "pending_action_count": len(pending),
                "has_important_risk": bool(
                    await session.scalar(
                        select(func.count())
                        .select_from(RiskFlag)
                        .join(Consultation)
                        .where(
                            and_(
                                Consultation.client_id == client_id,
                                RiskFlag.severity == "HIGH",
                                RiskFlag.resolved.is_(False),
                            )
                        )
                    )
                ),
                "current_status": note.counseling_note["client_status"] if note else None,
                "current_status_consultation_id": done.id if done else None,
                "pending_actions": [action_json(item) for item in pending],
                "recent_consultations": [
                    {
                        "id": item.id,
                        "client_id": item.client_id,
                        "consulted_at": utc(item.consulted_at),
                        "created_at": utc(item.created_at),
                        "status": item.status,
                        "summary": (await session.get(Analysis, item.id)).counseling_note["summary"]
                        if await session.get(Analysis, item.id)
                        else None,
                        "counseling_note_confirmed_at": utc(item.counseling_note_confirmed_at)
                        if item.counseling_note_confirmed_at
                        else None,
                    }
                    for item in recent
                ],
            }

    @app.get("/clients/{client_id}/consultations")
    async def consultation_list(
        client_id: int, status: str | None = None, limit: int = 20, offset: int = 0
    ):
        if not 1 <= limit <= 100 or offset < 0:
            raise api_error(422, "VALIDATION_ERROR", "페이지 값을 확인해주세요.")
        async with session_factory() as session:
            await required(session, Client, client_id, "내담자")
            query = select(Consultation).where(Consultation.client_id == client_id)
            if status:
                query = query.where(Consultation.status == status)
            total = (await session.scalar(select(func.count()).select_from(query.subquery()))) or 0
            records = (
                await session.scalars(
                    query.order_by(Consultation.consulted_at.desc(), Consultation.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            items = []
            for item in records:
                record = await session.get(Analysis, item.id)
                items.append(
                    {
                        "id": item.id,
                        "client_id": item.client_id,
                        "consulted_at": utc(item.consulted_at),
                        "created_at": utc(item.created_at),
                        "status": item.status,
                        "summary": record.counseling_note["summary"] if record else None,
                        "counseling_note_confirmed_at": utc(item.counseling_note_confirmed_at)
                        if item.counseling_note_confirmed_at
                        else None,
                    }
                )
            return {"items": items, "total": total, "limit": limit, "offset": offset}

    @app.post("/clients/{client_id}/consultations", status_code=202)
    async def upload_consultation(
        client_id: int, audio: UploadFile = File(...), consulted_at: datetime = Form(...)
    ):
        if consulted_at.tzinfo is None:
            raise api_error(422, "VALIDATION_ERROR", "시간대가 포함된 상담 시각이 필요합니다.")
        filename = audio.filename or "upload"
        data = await audio.read(settings.max_audio_bytes + 1)
        if len(data) > settings.max_audio_bytes:
            raise api_error(413, "FILE_TOO_LARGE", "파일 크기가 최대 허용량을 초과했습니다.")
        if not data:
            raise api_error(422, "INVALID_AUDIO", "빈 파일은 업로드할 수 없습니다.")
        if Path(filename).suffix.lower() not in {".wav", ".mp3", ".m4a", ".mp4", ".ogg", ".webm"}:
            raise api_error(415, "UNSUPPORTED_AUDIO_FORMAT", "지원하지 않는 오디오 형식입니다.")
        if not valid_audio(data, filename):
            raise api_error(422, "INVALID_AUDIO", "오디오 파일을 확인할 수 없습니다.")
        temp_root = Path(os.getenv("AUDIO_TEMP_DIR", "/tmp/social-worker-ax"))
        temp_root.mkdir(parents=True, exist_ok=True)
        path = temp_root / f"{uuid.uuid4().hex}{Path(filename).suffix.lower()}"
        path.write_bytes(data)
        async with session_factory() as session:
            await required(session, Client, client_id, "내담자")
            consultation = Consultation(
                client_id=client_id, consulted_at=consulted_at, status=ConsultationStatus.UPLOADED
            )
            session.add(consultation)
            await session.flush()
            session.add(
                ProcessingJob(
                    consultation_id=consultation.id,
                    stage="TRANSCRIBING",
                    payload={"path": str(path)},
                )
            )
            await session.commit()
            return JSONResponse(
                status_code=202,
                content={
                    "consultation_id": consultation.id,
                    "status": consultation.status,
                    "status_url": f"/consultations/{consultation.id}",
                },
                headers={"Location": f"/consultations/{consultation.id}"},
            )

    @app.get("/consultations/{consultation_id}")
    async def consultation_detail(consultation_id: int):
        async with session_factory() as session:
            return consultation_json(await required(session, Consultation, consultation_id, "상담"))

    @app.patch("/consultations/{consultation_id}/transcript")
    async def patch_transcript(consultation_id: int, body: TranscriptUpdate):
        async with session_factory() as session:
            item = await require_state(
                session, consultation_id, {ConsultationStatus.AWAITING_TRANSCRIPT_REVIEW}
            )
            item.transcript = body.transcript
            await session.commit()
            return consultation_json(item)

    @app.post("/consultations/{consultation_id}/transcript/confirm", status_code=202)
    async def confirm_transcript(consultation_id: int):
        async with session_factory() as session:
            item = await require_state(
                session, consultation_id, {ConsultationStatus.AWAITING_TRANSCRIPT_REVIEW}
            )
            item.transcript_confirmed_at = now()
            item.status = ConsultationStatus.GENERATING_NOTE
            session.add(ProcessingJob(consultation_id=item.id, stage="GENERATING_NOTE"))
            await session.commit()
            return {
                "consultation_id": item.id,
                "status": item.status,
                "status_url": f"/consultations/{item.id}",
            }

    @app.get("/consultations/{consultation_id}/counseling-note")
    async def get_note(consultation_id: int):
        async with session_factory() as session:
            item = await required(session, Consultation, consultation_id, "상담")
            record = await session.get(Analysis, item.id)
            if not record:
                raise api_error(
                    409,
                    "PROCESSING_FAILED"
                    if item.status == ConsultationStatus.FAILED
                    else "RESULT_NOT_READY",
                    "상담일지가 아직 준비되지 않았습니다.",
                )
            return note_json(record, item)

    @app.patch("/consultations/{consultation_id}/counseling-note")
    async def patch_note(consultation_id: int, body: NoteUpdate):
        async with session_factory() as session:
            item = await require_state(
                session, consultation_id, {ConsultationStatus.AWAITING_NOTE_REVIEW}
            )
            record = await required(session, Analysis, consultation_id, "상담일지")
            note = dict(record.counseling_note)
            for field, value in body.model_dump(exclude_unset=True).items():
                note[field] = value.model_dump() if hasattr(value, "model_dump") else value
            record.counseling_note = note
            await session.commit()
            return note_json(record, item)

    @app.post("/consultations/{consultation_id}/counseling-note/confirm", status_code=202)
    async def confirm_note(consultation_id: int):
        async with session_factory() as session:
            item = await require_state(
                session, consultation_id, {ConsultationStatus.AWAITING_NOTE_REVIEW}
            )
            item.counseling_note_confirmed_at = now()
            item.status = ConsultationStatus.ANALYZING
            session.add(ProcessingJob(consultation_id=item.id, stage="ANALYZING"))
            await session.commit()
            return {
                "consultation_id": item.id,
                "status": item.status,
                "status_url": f"/consultations/{item.id}",
            }

    @app.get("/consultations/{consultation_id}/analysis")
    async def get_analysis(consultation_id: int):
        async with session_factory() as session:
            item = await required(session, Consultation, consultation_id, "상담")
            record = await session.get(Analysis, item.id)
            if item.status != ConsultationStatus.DONE or not record or not record.analysis_json:
                raise api_error(
                    409,
                    "PROCESSING_FAILED"
                    if item.status == ConsultationStatus.FAILED
                    else "RESULT_NOT_READY",
                    "후속 분석 결과가 아직 준비되지 않았습니다.",
                )
            risks = (
                await session.scalars(
                    select(RiskFlag)
                    .where(RiskFlag.consultation_id == item.id)
                    .order_by(RiskFlag.id)
                )
            ).all()
            actions = (
                await session.scalars(
                    select(ActionItem)
                    .where(ActionItem.consultation_id == item.id)
                    .order_by(ActionItem.id)
                )
            ).all()
            return {
                "consultation_id": item.id,
                "summary": record.counseling_note["summary"],
                "client_status": record.counseling_note["client_status"],
                **record.analysis_json,
                "risk_flags": [risk_json(risk) for risk in risks],
                "recommended_actions": [action_json(action) for action in actions],
                "created_at": utc(record.analyzed_at or record.created_at),
            }

    @app.get("/clients/{client_id}/actions")
    async def actions(
        client_id: int,
        status: str | None = None,
        priority: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ):
        if not 1 <= limit <= 100 or offset < 0:
            raise api_error(422, "VALIDATION_ERROR", "페이지 값을 확인해주세요.")
        async with session_factory() as session:
            await required(session, Client, client_id, "내담자")
            query = select(ActionItem).where(ActionItem.client_id == client_id)
            if status:
                query = query.where(ActionItem.status == status)
            if priority:
                query = query.where(ActionItem.priority == priority)
            total = (await session.scalar(select(func.count()).select_from(query.subquery()))) or 0
            values = (
                await session.scalars(
                    query.order_by(ActionItem.due_date.asc().nulls_last(), ActionItem.id)
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return {
                "items": [action_json(value) for value in values],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    @app.patch("/actions/{action_id}")
    async def patch_action(action_id: int, body: ActionUpdate):
        async with session_factory() as session:
            item = await required(session, ActionItem, action_id, "Action")
            item.status = body.status
            await session.commit()
            return action_json(item)

    @app.post("/clients/{client_id}/case-report")
    async def case_report(client_id: int, body: CaseReportRequest | None = None):
        body = body or CaseReportRequest()
        async with session_factory() as session:
            client = await required(session, Client, client_id, "내담자")
            records = (
                await session.execute(
                    select(Consultation, Analysis)
                    .join(Analysis, Analysis.consultation_id == Consultation.id)
                    .where(
                        and_(
                            Consultation.client_id == client_id,
                            Consultation.status == ConsultationStatus.DONE,
                        )
                    )
                    .order_by(Consultation.consulted_at.desc(), Consultation.id.desc())
                    .limit(body.consultation_limit)
                )
            ).all()
            if not records:
                raise api_error(409, "INSUFFICIENT_DATA", "완료된 상담 기록이 없습니다.")
            actions = (
                await session.scalars(
                    select(ActionItem).where(
                        and_(ActionItem.client_id == client_id, ActionItem.status == "TODO")
                    )
                )
            ).all()
            risks = (
                await session.scalars(
                    select(RiskFlag)
                    .join(Consultation)
                    .where(and_(Consultation.client_id == client_id, RiskFlag.resolved.is_(False)))
                )
            ).all()
            source = [
                {
                    "id": c.id,
                    "consulted_at": utc(c.consulted_at),
                    "summary": a.counseling_note["summary"],
                    "client_status": a.counseling_note["client_status"],
                }
                for c, a in records
            ]
            try:
                report = await asyncio.wait_for(
                    app.state.ai.report(
                        source, [action_json(a) for a in actions], [risk_json(r) for r in risks]
                    ),
                    timeout=settings.case_report_timeout_seconds,
                )
            except TimeoutError:
                raise api_error(504, "AI_TIMEOUT", "리포트 생성 시간이 초과되었습니다.") from None
            except AIServiceError:
                raise api_error(
                    502, "AI_SERVICE_ERROR", "리포트 생성 서비스 오류가 발생했습니다."
                ) from None
            report["client_overview"] = report.get("client_overview") or f"{client.name}"
            report["recent_status"] = report.get("recent_status") or source[0]["client_status"]
            report["timeline"] = report.get("timeline") or [
                {
                    "consultation_id": x["id"],
                    "consulted_at": x["consulted_at"],
                    "description": x["summary"],
                }
                for x in reversed(source)
            ]
            for key in (
                "current_risks",
                "support_status",
                "unresolved_issues",
                "discussion_points",
            ):
                report.setdefault(key, [])
            return {
                "client_id": client_id,
                "consultation_ids": [c.id for c, _ in records],
                "report": report,
                "generated_at": utc(now()),
            }

    return app


app = create_app()
