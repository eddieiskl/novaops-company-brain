from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .store import RenewalStore


class NotificationAdapter(Protocol):
    def send(
        self,
        *,
        run_id: str,
        idempotency_key: str,
        channel: str,
        recipient: str,
        kind: str,
        subject: str,
        body: str,
        created_at: str,
    ) -> str: ...


class ProviderEmailAdapter(Protocol):
    def send(
        self, *, run_id: str, recipient: str, subject: str, body: str, created_at: str
    ) -> str: ...

    def fetch_reply(self, fixture_id: str) -> str: ...


class MockNotificationAdapter:
    def __init__(self, store: RenewalStore) -> None:
        self.store = store

    def send(self, **message) -> str:
        return self.store.enqueue(**message)


class MockProviderEmailAdapter:
    def __init__(
        self, store: RenewalStore, replies: dict[str, str] | None = None
    ) -> None:
        self.store = store
        self.replies = replies or self._fixture_replies()

    def send(
        self, *, run_id: str, recipient: str, subject: str, body: str, created_at: str
    ) -> str:
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
        root = (
            Path(__file__).resolve().parents[1]
            / "novaops-enterprise-agent-dataset"
            / "workflows"
            / "renewal"
            / "provider_replies"
        )
        return {
            path.stem: path.read_text(encoding="utf-8") for path in root.glob("*.eml")
        }


class OutboxDispatcher:
    """Delivery state machine for explicitly provided transports.

    The transaction records 'sending' before invoking a transport. After a process
    interruption, sending is uncertain and is never automatically retried.
    """

    def __init__(self, store, transport):
        self.store, self.transport = store, transport

    def recover(self):
        with self.store.atomic():
            self.store.db.execute(
                "UPDATE renewal_outbox SET delivery_status='uncertain' WHERE delivery_status='sending'"
            )

    def deliver(self, message_id):
        with self.store.atomic():
            row = self.store.db.execute(
                "SELECT * FROM renewal_outbox WHERE message_id=?", (message_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Unknown outbox message")
            if row["delivery_status"] != "queued":
                return row["delivery_status"]
            self.store.db.execute(
                "UPDATE renewal_outbox SET delivery_status='sending' WHERE message_id=?",
                (message_id,),
            )
            message = dict(row)
        try:
            receipt = self.transport(message)
            outcome = "delivered" if receipt is True else "uncertain"
        except Exception:
            outcome = "uncertain"
        with self.store.atomic():
            self.store.set_delivery(message_id, outcome)
        return outcome
