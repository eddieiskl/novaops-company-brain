from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Iterator


_client: ContextVar[Any | None] = ContextVar("novaops_observability_client", default=None)
_request_id: ContextVar[str | None] = ContextVar("novaops_request_id", default=None)


class NullObservation:
    """Langfuse-compatible no-op used outside a traced evaluation run."""

    def update(self, **_: Any) -> None:
        return None


@contextmanager
def bind_observer(client: Any, request_id: str | None) -> Iterator[None]:
    client_token: Token = _client.set(client)
    request_token: Token = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(request_token)
        _client.reset(client_token)


@contextmanager
def observe(
    name: str,
    *,
    as_type: str = "span",
    input: Any = None,
    metadata: dict[str, Any] | None = None,
    **attributes: Any,
) -> Iterator[Any]:
    """Create an observation around the work that is actually executing."""

    client = _client.get()
    if client is None:
        yield NullObservation()
        return

    observation_metadata = dict(metadata or {})
    request_id = _request_id.get()
    if request_id:
        observation_metadata.setdefault("request_id", request_id)
    kwargs: dict[str, Any] = {"name": name, "as_type": as_type}
    if input is not None:
        kwargs["input"] = input
    if observation_metadata:
        kwargs["metadata"] = observation_metadata
    kwargs.update(attributes)
    with client.start_as_current_observation(**kwargs) as observation:
        yield observation
