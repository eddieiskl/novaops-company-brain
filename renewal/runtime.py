from __future__ import annotations

import os

from model_client import get_model

from .extractor import ProviderDecisionExtractor
from .workflow import build_renewal_workflow


class DeterministicProviderModel:
    model_id = "deterministic-provider-fixture"

    def extract_with_tool(self, prompt: str, **_) -> dict:
        common = {
            "contract_id": "C001",
            "new_seat_limit": 50,
            "annual_cost_usd": 22000,
            "term_start_date": "2026-07-21",
            "term_end_date": "2027-07-20",
        }
        if "final confirmation" in prompt and "RX-WEBEX-2026-8841" in prompt:
            return {
                **common,
                "decision": "approved",
                "confirmation_id": "RX-WEBEX-2026-8841",
                "conditions": [],
            }
        if "not final approval" in prompt:
            return {
                **common,
                "decision": "conditional",
                "confirmation_id": None,
                "conditions": ["Signed order form", "Written Finance acceptance"],
            }
        if "not approve" in prompt or "declined" in prompt:
            return {
                **common,
                "decision": "rejected",
                "confirmation_id": None,
                "conditions": [],
            }
        return {
            "contract_id": None,
            "decision": "ambiguous",
            "confirmation_id": None,
            "new_seat_limit": 50 if "50 seats" in prompt else None,
            "annual_cost_usd": None,
            "term_start_date": None,
            "term_end_date": None,
            "conditions": ["Final commercial details and confirmation are pending"],
        }


def build_renewal_workflow_from_env(
    *, replies: dict[str, str] | None = None, security_reviewer_id: str | None = None
):
    mode = os.getenv("NOVAOPS_ANSWER_MODE", "deterministic").strip().lower()
    model = (
        get_model() if mode in {"bedrock", "gateway"} else DeterministicProviderModel()
    )
    if mode not in {"deterministic", "bedrock", "gateway"}:
        raise ValueError(
            "NOVAOPS_ANSWER_MODE must be 'deterministic', 'bedrock', or 'gateway'."
        )
    return build_renewal_workflow(
        extractor=ProviderDecisionExtractor(model=model),
        replies=replies,
        security_reviewer_id=security_reviewer_id
        or os.getenv("NOVAOPS_RENEWAL_SECURITY_REVIEWER"),
    )
