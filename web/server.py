from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from threading import Lock
import uuid
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maya import CallerContext, MayaRuntime, build_dashboard_snapshot
from maya import ops
from company_brain import CompanyBrainAgent, LocalRuleRequestGuard


STATIC_DIR = Path(__file__).resolve().parent / "static"
SECURITY_DEMO_LOCK = Lock()


def showcase_payload() -> dict[str, object]:
    return {
        "release_commit": "lesson-13",
        "metrics": [
            {"label": "Workflows", "value": "4 / 4", "note": "Required + optional"},
            {"label": "Tests", "value": "87 / 87", "note": "Full suite"},
            {"label": "Evaluation", "value": "33 / 33", "note": "Optional-inclusive"},
            {"label": "Deterministic", "value": "243 × 1.0", "note": "Binding scores"},
            {"label": "Security", "value": "16 / 16", "note": "Live guard cases"},
        ],
        "workflows": [
            {
                "name": "Maya",
                "domain": "HR onboarding",
                "proof": "Cited retrieval and a read-only access handoff.",
                "boundary": "Chat cannot grant access or expose manager-only evidence.",
            },
            {
                "name": "Webex",
                "domain": "IT operations",
                "proof": "Durable approval state, reused records, and replay safety.",
                "boundary": "A write releases only after a recorded, assigned approval.",
            },
            {
                "name": "Vendor",
                "domain": "CRM extraction",
                "proof": "One forced-tool call with schema validation and focused follow-up.",
                "boundary": "Missing required fields stay missing; the model cannot invent them.",
            },
            {
                "name": "Renewal",
                "domain": "Contract renewal",
                "proof": "Persistent schedule, proposal, outbox, audit, and notifications.",
                "boundary": "Only an exact approved proposal can create exactly-once effects.",
            },
        ],
        "control_chain": ["Retrieve", "Validate", "Authorize", "Execute", "Observe", "Evaluate"],
        "security_metrics": [
            {"label": "Guard decisions", "value": "16 / 16", "note": "Exact live decisions"},
            {"label": "Attacks allowed", "value": "0 / 8", "note": "Frozen attack set"},
            {"label": "Durable changes", "value": "0", "note": "Across blocked cases"},
            {"label": "Index restored", "value": "634 / 634", "note": "Owned poison removed"},
        ],
        "proof": [
            {"label": "Pytest", "value": "87 / 87", "note": "Reliability and durability"},
            {"label": "Golden records", "value": "33 / 33", "note": "Required + optional"},
            {"label": "API scores", "value": "243", "note": "Every result is 1.0"},
            {"label": "Advisory judge", "value": "0.897", "note": "99 separate scores"},
            {"label": "GitHub Actions", "value": "Passed", "note": "41-second CI run"},
        ],
        "evidence": [
            {"claim": "Grounded answers", "source": "Citations and permission-filtered retrieval", "kind": "Binding"},
            {"claim": "Durable approval", "source": "Restart and resume tests plus SQLite state", "kind": "Binding"},
            {"claim": "Exactly-once effects", "source": "Replayed renewal events and idempotent outbox", "kind": "Binding"},
            {"claim": "Observable behavior", "source": "33 indexed traces and 42 tool observations", "kind": "Trace"},
            {"claim": "Safe deployment", "source": "Three non-root images, health checks, local Compose", "kind": "Packaging"},
            {"claim": "Poison resistance", "source": "Source manifest, semantic guard, quarantine, and exact cleanup", "kind": "Security"},
        ],
    }


def security_demo(message: str) -> dict[str, object]:
    """Run one local, synthetic guardrail probe with an explicit state delta."""
    if not message.strip():
        raise ValueError("Enter a request to test.")
    if len(message) > 12_000:
        raise ValueError("Security demo input is limited to 12,000 characters.")
    caller = CallerContext("E004", "UG_HR")
    with SECURITY_DEMO_LOCK:
        before = int(ops.conn().execute("SELECT COUNT(*) FROM access_requests").fetchone()[0])
        result = CompanyBrainAgent(request_guard=LocalRuleRequestGuard()).handle_turn(
            f"security-demo-{uuid.uuid4().hex[:10]}",
            caller,
            message,
        )
        after = int(ops.conn().execute("SELECT COUNT(*) FROM access_requests").fetchone()[0])
    return {
        "guard": result.guard_decision,
        "status": result.status,
        "scope": result.scope,
        "intent": result.intent,
        "answer": result.answer,
        "tool_sequence": result.tool_sequence,
        "durable_access_requests_before": before,
        "durable_access_requests_after": after,
    }


def to_jsonable(value):
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value


class MayaChatHandler(SimpleHTTPRequestHandler):
    runtime = MayaRuntime()
    turns_by_thread: dict[str, int] = {}

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        target = parsed.path.lstrip("/") or "index.html"
        return str(STATIC_DIR / target)

    def do_GET(self):
        if self.path == "/api/showcase":
            self._send_json(showcase_payload())
            return
        if self.path == "/api/status":
            self._send_json({"ok": True, "threads": len(self.turns_by_thread), "retriever": to_jsonable(self.runtime.status())})
            return
        if self.path == "/api/retriever":
            self._send_json({"ok": True, "retriever": to_jsonable(self.runtime.status())})
            return
        if self.path == "/api/dashboard":
            self._send_json(
                {
                    "ok": True,
                    "retriever": to_jsonable(self.runtime.status()),
                    "dashboard": build_dashboard_snapshot(self.runtime.retriever),
                }
            )
            return
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/chat":
            self._handle_chat()
            return
        if self.path == "/api/retriever":
            self._handle_retriever()
            return
        if self.path == "/api/security-demo":
            self._handle_security_demo()
            return
        self.send_error(404, "Not found")

    def _handle_chat(self) -> None:
        try:
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            thread_id = payload.get("thread_id") or "maya-ui-session"
            caller_payload = payload.get("caller") or {"employee_id": "E004", "user_group": "UG_HR"}
            caller = CallerContext(**caller_payload)
            turn = int(payload.get("turn") or self.turns_by_thread.get(thread_id, 0) + 1)
            message = str(payload.get("message") or "")
            result = self.runtime.agent.handle_turn_sync(thread_id, caller, turn, message)
            self.turns_by_thread[thread_id] = max(turn, self.turns_by_thread.get(thread_id, 0))
            self._send_json(
                {
                    "ok": True,
                    "thread_id": thread_id,
                    "turn": turn,
                    "retriever": to_jsonable(self.runtime.status()),
                    "result": to_jsonable(result),
                }
            )
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=500)

    def _handle_retriever(self) -> None:
        try:
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            status = self.runtime.set_mode(str(payload.get("mode") or "memory"))
            self.turns_by_thread.clear()
            self._send_json({"ok": True, "retriever": to_jsonable(status), "threads_reset": True})
        except Exception as exc:
            self._send_json(
                {"ok": False, "error": str(exc), "retriever": to_jsonable(self.runtime.status())},
                status=400,
            )

    def _handle_security_demo(self) -> None:
        try:
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            self._send_json({"ok": True, "result": security_demo(str(payload.get("message") or ""))})
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)

    def _send_json(self, payload, status=200) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 4180), MayaChatHandler)
    print("NovaOps Company Brain showcase running at http://127.0.0.1:4180")
    server.serve_forever()
