"""Explicit recovery for legacy RUNNING jobs after the old deployment is stopped.

No API endpoint is added. Preview is read-only; --apply requires the operator to
confirm that the previous deployment cannot still commit a late AI response.
"""

import argparse
import asyncio

from sqlalchemy import func, select

from .core import Settings
from .db import create_database
from .models import ActionItem, Analysis, Consultation, ProcessingJob, RiskFlag


async def recover(factory, consultation_id: int, *, apply: bool = False) -> str:
    async with factory() as session, session.begin():
        consultation = await session.scalar(
            select(Consultation).where(Consultation.id == consultation_id).with_for_update()
        )
        if not consultation or consultation.status not in {"ANALYZING", "GENERATING_NOTE"}:
            raise ValueError("Only stalled note/analysis consultations can be recovered")
        job = await session.scalar(
            select(ProcessingJob)
            .where(
                ProcessingJob.consultation_id == consultation_id,
                ProcessingJob.stage == consultation.status,
            )
            .with_for_update()
        )
        if not job or job.state not in {"RUNNING", "QUEUED"}:
            raise ValueError("No recoverable job exists")
        if job.state == "RUNNING" and (job.payload or {}).get("worker_version"):
            raise ValueError("The updated worker owns this job; refusing duplicate execution")
        record = await session.get(Analysis, consultation_id)
        if consultation.status == "ANALYZING":
            if (
                not record
                or record.analysis_json is not None
                or consultation.counseling_note_confirmed_at is None
            ):
                raise ValueError("Analysis input/result is inconsistent; refusing recovery")
            for model in (RiskFlag, ActionItem):
                count = await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(
                        model.consultation_id == consultation_id,
                    )
                )
                if count:
                    raise ValueError("Partial results exist; refusing to create duplicates")
        elif record or consultation.transcript_confirmed_at is None:
            raise ValueError("Note input/result is inconsistent; refusing recovery")
        if job.state == "QUEUED":
            return f"consultation_id={consultation_id} job_id={job.id} already_queued"
        if apply:
            job.state = "QUEUED"
        return (
            f"consultation_id={consultation_id} job_id={job.id} "
            f"stage={job.stage} {'requeued' if apply else 'eligible'}"
        )


async def run(args):
    engine, factory = create_database(Settings().database_url)
    try:
        print(await recover(factory, args.consultation_id, apply=args.apply))
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consultation-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--previous-deployment-stopped", action="store_true")
    args = parser.parse_args()
    if args.consultation_id <= 0:
        parser.error("consultation-id must be positive")
    if args.apply and not args.previous_deployment_stopped:
        parser.error("Stop the previous deployment, then use --previous-deployment-stopped")
    try:
        asyncio.run(run(args))
    except ValueError as exc:
        parser.exit(1, f"Recovery refused: {exc}\n")


if __name__ == "__main__":
    main()
