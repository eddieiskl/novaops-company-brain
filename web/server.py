from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from maya import CallerContext, MayaRuntime, build_dashboard_snapshot


STATIC_DIR = Path(__file__).resolve().parent / "static"


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

    def _send_json(self, payload, status=200) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 4180), MayaChatHandler)
    print("Maya onboarding chat running at http://127.0.0.1:4180")
    server.serve_forever()
