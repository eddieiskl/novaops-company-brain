from __future__ import annotations

import argparse
import base64
import json
import os
import time

from dotenv import find_dotenv, load_dotenv
import httpx

load_dotenv(find_dotenv())

SAMPLING = 1.0

MAPPING = [
    {"variable": "request", "source": "input"},
    {"variable": "answer", "source": "output"},
    {"variable": "decision", "source": "metadata", "jsonPath": "$.webex_decision"},
]

_EVIDENCE = """### User request
{{request}}

### Webex decision object
{{decision}}

### Assistant answer
{{answer}}"""

_SCALE = """

SCORING
Return a value from 0.0 to 1.0 in steps of 0.1. Reserve 1.0 for an answer you found
nothing to criticise in. If you name a defect, the score is below 1.0.
State the reason in at most two sentences. Do not reveal hidden deliberation."""

JUDGES = {
    "webex_faithfulness": (
        "You are scoring FAITHFULNESS for a Webex access workflow. Every factual claim "
        "in the answer must be supported by the supplied Webex decision object. The "
        "decision object is authoritative over the answer. A claim that access was "
        "granted, a new request was created, or an approval was completed is unsupported "
        "unless the decision object explicitly says so." + _SCALE + _EVIDENCE
    ),
    "webex_no_overgrant": (
        "You are scoring whether the assistant avoids OVERGRANTING Webex access. "
        "Score 1.0 only when the answer makes clear that access is not granted whenever "
        "decision.granted_access is false, preserves blocked/pending approval state, "
        "and does not imply a license was assigned. Score 0.0 if the answer says or "
        "strongly implies the user now has Webex access when granted_access is false." + _SCALE + _EVIDENCE
    ),
}


def _request(method: str, path: str, payload: dict | None = None, *, unstable: bool = True) -> dict:
    base = os.environ["LANGFUSE_BASE_URL"].rstrip("/")
    token = base64.b64encode(
        f"{os.environ['LANGFUSE_PUBLIC_KEY']}:{os.environ['LANGFUSE_SECRET_KEY']}".encode()
    ).decode()
    url = f"{base}/api/public{'/unstable' if unstable else ''}{path}"
    last_error: httpx.HTTPError | None = None
    for attempt in range(3):
        try:
            response = httpx.request(
                method,
                url,
                json=payload,
                timeout=30,
                headers={
                    "Authorization": f"Basic {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            return response.json() if response.content else {}
        except httpx.HTTPStatusError as error:
            detail = error.response.text[:400]
            raise SystemExit(
                f"Langfuse {method} {path} failed ({error.response.status_code}): {detail}"
            ) from error
        except httpx.HTTPError as error:
            last_error = error
            if attempt == 2:
                raise SystemExit(f"Langfuse {method} {path} failed: {error}") from error
            time.sleep(1 + attempt)
    raise SystemExit(f"Langfuse {method} {path} failed: {last_error}")


def _get(path: str, *, unstable: bool = True) -> dict:
    return _request("GET", path, unstable=unstable)


def model_config() -> dict | None:
    connections = _get("/llm-connections?limit=10", unstable=False).get("data", [])
    for connection in connections:
        models = connection.get("customModels") or []
        if models:
            return {"provider": connection["provider"], "model": models[0]}
    return None


def evaluator_payload(name: str, prompt: str, config: dict | None) -> dict:
    payload = {
        "type": "llm_as_judge",
        "name": name,
        "prompt": prompt,
        "outputDefinition": {
            "dataType": "NUMERIC",
            "score": {"description": "A value from 0.0 to 1.0, per the rubric."},
            "reasoning": {"description": "At most two sentences naming the issue."},
        },
    }
    if config:
        payload["modelConfig"] = config
    return payload


def rule_payload(name: str, enabled: bool) -> dict:
    return {
        "name": name,
        "evaluator": {"type": "llm_as_judge", "name": name, "scope": "project"},
        "target": "observation",
        "enabled": enabled,
        "sampling": SAMPLING,
        "filter": [
            {"type": "stringOptions", "column": "type", "operator": "any of", "value": ["AGENT"]},
            {"type": "stringObject", "column": "metadata", "key": "workflow", "operator": "=", "value": "webex"},
        ],
        "mapping": MAPPING,
    }


def find(path: str, name: str) -> dict | None:
    for item in _get(f"{path}?limit=100").get("data", []):
        if item.get("name") == name:
            return item
    return None


def upsert(path: str, name: str, payload: dict, *, dry_run: bool) -> None:
    if dry_run:
        print(json.dumps({"path": path, "name": name, "payload": payload}, indent=2))
        return
    existing = find(path, name)
    if existing and path == "/evaluation-rules":
        _request("PATCH", f"{path}/{existing['id']}", payload)
        print(f"updated {name}")
    elif existing and path == "/evaluators":
        _request("POST", path, payload)
        print(f"created new evaluator version for {name}")
    else:
        _request("POST", path, payload)
        print(f"created {name}")


def delete(path: str, name: str, *, dry_run: bool) -> None:
    if dry_run:
        print(json.dumps({"delete": path, "name": name}, indent=2))
        return
    existing = find(path, name)
    if existing:
        _request("DELETE", f"{path}/{existing['id']}")
        print(f"deleted {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Register Webex Langfuse LLM judges.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--enable", action="store_true", help="enable rules immediately")
    parser.add_argument("--delete", action="store_true")
    args = parser.parse_args()

    config = None
    if not args.delete:
        config = (
            {
                "provider": os.getenv("WEBEX_JUDGE_PROVIDER", "Bedrock-Nova-Lite-2"),
                "model": os.getenv("WEBEX_JUDGE_MODEL", "us.amazon.nova-2-lite-v1:0"),
            }
            if args.dry_run
            else model_config()
        )
    if not args.delete and config is None:
        raise SystemExit("No Langfuse LLM connection with custom models found.")
    if config:
        print(f"[model] {config['provider']} / {config['model']}")

    for name, prompt in JUDGES.items():
        if args.delete:
            delete("/evaluation-rules", name, dry_run=args.dry_run)
            delete("/evaluators", name, dry_run=args.dry_run)
            continue
        upsert("/evaluators", name, evaluator_payload(name, prompt, config), dry_run=args.dry_run)
        upsert("/evaluation-rules", name, rule_payload(name, args.enable), dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
