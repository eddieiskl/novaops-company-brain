from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .store import RenewalStore


class NotificationAdapter(Protocol):
    def send(self, *, run_id: str, idempotency_key: str, channel: str, recipient: str, kind: str, subject: str, body: str, created_at: str) -> str:
        ...


class ProviderEmailAdapter(Protocol):
    def send(self, *, run_id: str, recipient: str, subject: str, body: str, created_at: str) -> str:
        ...

    def fetch_reply(self, fixture_id: str) -> str:
        ...


class MockNotificationAdapter:
    def __init__(self, store: RenewalStore) -> None:
        self.store = store

    def send(self, **message) -> str:
        return self.store.enqueue(**message)


class MockProviderEmailAdapter:
    def __init__(self, store: RenewalStore, replies: dict[str, str] | None = None) -> None:
        self.store = store
        self.replies = replies or self._fixture_replies()

    def send(self, *, run_id: str, recipient: str, subject: str, body: str, created_at: str) -> str:
        return self.store.enqueue(
            run_id=run_id,
            idempotency_key=f"{run_id}:provider-request",
            channel="email",
            recipient=recipient,
            kind="provider_renewal_request",
            subject=subject,
            body=body,
            created_at=created_at,
        )

    def fetch_reply(self, fixture_id: str) -> str:
        try:
            return self.replies[fixture_id]
        except KeyError as exc:
            raise ValueError(f"Unknown provider reply fixture: {fixture_id}") from exc

    @staticmethod
    def _fixture_replies() -> dict[str, str]:
        root = Path(__file__).resolve().parents[1] / "novaops-enterprise-agent-dataset" / "workflows" / "renewal" / "provider_replies"
        return {path.stem: path.read_text(encoding="utf-8") for path in root.glob("*.eml")}
