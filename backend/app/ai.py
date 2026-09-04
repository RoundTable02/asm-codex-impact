from __future__ import annotations

import json
from collections.abc import Sequence

from openai import AsyncOpenAI

from .core import Settings, empty_status


class AIServiceError(Exception):
    pass


class AIService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            AsyncOpenAI(api_key=settings.openai_api_key) if settings.ai_mode == "openai" else None
        )

    async def transcribe(self, audio: bytes, filename: str) -> str:
        if self.settings.ai_mode == "fake":
            return "[테스트 전사문] 합성 음성 파일이 접수되었습니다."
        if not self.client:
            raise AIServiceError("OpenAI 설정이 없습니다.")
        try:
            response = await self.client.audio.transcriptions.create(
                model=self.settings.openai_stt_model,
                file=(filename, audio),
                language="ko",
            )
            return response.text.strip()
        except Exception as exc:  # Provider details must never be exposed to callers.
            raise AIServiceError("STT 호출에 실패했습니다.") from exc

    async def note(self, transcript: str) -> dict:
        if self.settings.ai_mode == "fake":
            return {
                "summary": transcript[:5000],
                "main_contents": [transcript[:2000]],
                "client_status": empty_status(),
            }
        prompt = (
            "Return only JSON with summary (string), main_contents (string[]), and client_status "
            "with exactly health, nutrition, emotion, family, housing, social string arrays. "
            "Do not diagnose; use UNKNOWN/확인 필요 when unsupported. Transcript:\n" + transcript
        )
        return await self._json(prompt)

    async def analysis(self, note: dict, transcript: str, previous: Sequence[dict]) -> dict:
        if self.settings.ai_mode == "fake":
            changes = []
            for category, values in note["client_status"].items():
                if values:
                    changes.append(
                        {
                            "category": category.upper(),
                            "change": "UNKNOWN",
                            "previous": None,
                            "current": values[0],
                            "description": "비교 근거가 부족하여 확인이 필요합니다.",
                        }
                    )
            return {
                "important_changes": changes,
                "risk_flags": [],
                "unresolved_issues": [],
                "recommended_actions": [],
            }
        prompt = (
            "Return only JSON with important_changes, risk_flags, unresolved_issues, "
            "recommended_actions. Base conclusions on final counseling note, not prior draft. "
            "Evidence must be a literal excerpt from transcript or null. Never diagnose. "
            "Final note:\n"
            + json.dumps(note, ensure_ascii=False)
            + "\nTranscript:\n"
            + transcript
            + "\nPrevious records:\n"
            + json.dumps(list(previous), ensure_ascii=False)
        )
        return await self._json(prompt)

    async def report(
        self, records: Sequence[dict], actions: Sequence[dict], risks: Sequence[dict]
    ) -> dict:
        if self.settings.ai_mode == "fake":
            latest = records[0]
            return {
                "client_overview": "가명 내담자",
                "recent_status": latest["client_status"],
                "timeline": [],
                "current_risks": [],
                "support_status": [],
                "unresolved_issues": [],
                "discussion_points": [],
            }
        prompt = (
            "Return only JSON case report with client_overview, recent_status, timeline, "
            "current_risks, support_status, unresolved_issues, discussion_points. "
            "Do not invent support facts. Records:\n"
        )
        return await self._json(prompt + json.dumps(list(records), ensure_ascii=False))

    async def _json(self, prompt: str) -> dict:
        if not self.client:
            raise AIServiceError("OpenAI 설정이 없습니다.")
        try:
            response = await self.client.responses.create(
                model=self.settings.openai_llm_model,
                input=prompt,
                text={"format": {"type": "json_object"}},
            )
            parsed = json.loads(response.output_text)
            if not isinstance(parsed, dict):
                raise ValueError("object required")
            return parsed
        except Exception as exc:
            raise AIServiceError("AI 응답을 처리하지 못했습니다.") from exc
