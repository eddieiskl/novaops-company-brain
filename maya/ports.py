from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from typing import Protocol

from model_client import get_model
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model_client import BedrockModelClient

from .schemas import PendingAccessResult, WebexHandoff


class AnswerPort(Protocol):
    async def answer(self, prompt: str) -> str:
        ...


class OpenAIAnswerPort:
    """Optional model-backed answer port for live Maya demos."""

    def __init__(self, model: str) -> None:
        self.model = model

    async def answer(self, prompt: str) -> str:
        return await asyncio.to_thread(self._answer_sync, prompt)

    def _answer_sync(self, prompt: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install openai before enabling MAYA_ANSWER_MODE=model.") from exc

        response = OpenAI().responses.create(model=self.model, input=prompt)
        output_text = getattr(response, "output_text", None)
        if output_text:
            return str(output_text).strip()
        return str(response).strip()


class BedrockAnswerPort:
    """Production answer port using Nova 2 Lite through Bedrock Converse."""

    def __init__(self, model: BedrockModelClient | None = None) -> None:
        self.model = model or get_model()

    async def answer(self, prompt: str) -> str:
        from company_brain.instrumentation import observe

        system = (
            "You are the NovaOps company brain. Use only supplied evidence and records. "
            "Cite each factual claim, distinguish observed facts from recommendations, "
            "and never claim an action happened unless application state proves it."
        )
        with observe(
            "bedrock_answer",
            as_type="generation",
            input={"prompt": prompt, "system": system},
            metadata={"region": self.model.region},
            model=self.model.model_id,
            model_parameters={
                "max_tokens": self.model.max_tokens,
                "temperature": self.model.temperature,
            },
        ) as generation:
            try:
                answer = await asyncio.to_thread(self.model.generate, prompt, system=system)
            except Exception as exc:
                generation.update(
                    output={"error": str(exc), "error_type": type(exc).__name__},
                    metadata={"completed": False, "model": self.model.model_id},
                )
                raise
            generation.update(
                output={"answer": answer},
                metadata={"completed": True, "model": self.model.model_id},
            )
            return answer


class WebexPort(Protocol):
    async def request_access(self, handoff: WebexHandoff) -> PendingAccessResult:
        ...


class FakeWebexPort:
    """Deterministic Webex workflow test double with idempotency."""

    def __init__(self) -> None:
        self.calls: list[WebexHandoff] = []
        self._results: dict[str, PendingAccessResult] = {}

    async def request_access(self, handoff: WebexHandoff) -> PendingAccessResult:
        if handoff.idempotency_key in self._results:
            return self._results[handoff.idempotency_key]

        request_id = f"WX-{len(self.calls) + 1:03d}"
        result = PendingAccessResult(
            request_id=request_id,
            status="pending",
            idempotency_key=handoff.idempotency_key,
        )
        self.calls.append(handoff)
        self._results[handoff.idempotency_key] = result
        return result


class Lesson9ApprovalWebexPort:
    """Adapter from Maya's typed handoff to a Lesson 9-style pending request.

    The final project is intentionally standalone.  Callers can still provide a
    Lesson 9 server directory to exercise the original lab database, while the
    default uses a small in-process compatibility backend with the same response
    shape.  Maya's idempotency cache remains the source of duplicate suppression.
    """

    def __init__(self, lesson9_server_dir: Path | None = None) -> None:
        self.lesson9_server_dir = lesson9_server_dir
        self.calls: list[WebexHandoff] = []
        self._results: dict[str, PendingAccessResult] = {}
        self._next_request_number = 5

    async def request_access(self, handoff: WebexHandoff) -> PendingAccessResult:
        if handoff.idempotency_key in self._results:
            return self._results[handoff.idempotency_key]

        db = self._load_db_module()
        created = db.create_access_request(
            handoff.employee_id,
            handoff.software,
            handoff.business_reason,
        )
        result = PendingAccessResult(
            request_id=str(created["request_id"]),
            status=str(created["status"]),
            idempotency_key=handoff.idempotency_key,
        )
        self.calls.append(handoff)
        self._results[handoff.idempotency_key] = result
        return result

    def _load_db_module(self):
        if self.lesson9_server_dir is None:
            return self
        db_path = self.lesson9_server_dir / "db.py"
        if not db_path.exists():
            raise RuntimeError(f"Lesson 9 approval db.py not found at {db_path}.")
        spec = importlib.util.spec_from_file_location("maya_lesson9_approval_db", db_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load Lesson 9 approval db.py from {db_path}.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def create_access_request(
        self,
        employee_id: str,
        software: str,
        business_justification: str,
    ) -> dict[str, str]:
        """Return the original lab's pending-request shape without course files."""
        request_id = f"AR{self._next_request_number:03d}"
        self._next_request_number += 1
        return {
            "request_id": request_id,
            "employee_id": employee_id,
            "system_name": software,
            "business_justification": business_justification,
            "status": "pending_approval",
        }
