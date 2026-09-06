from __future__ import annotations

import os

from model_client import BedrockModelClient

from .extractor import VendorExtractor


class DeterministicVendorModel:
    """Offline development double for the three supplied synthetic source shapes."""

    model_id = "deterministic-vendor-fixture"

    def extract_with_tool(self, prompt: str, **_) -> dict:
        if "HelioDesk" in prompt:
            return {"record": {
                "vendor_name": "HelioDesk", "legal_name": "HelioDesk Technologies Ltd.",
                "primary_contact_name": "Ava Patel", "primary_contact_email": "ava.patel@heliodesk.example",
                "service_category": "Customer support quality assurance SaaS", "internal_owner_department": "Customer Success",
                "annual_cost_usd": 28800, "contract_start_date": "2026-10-01", "contract_end_date": "2027-09-30",
                "renewal_type": "manual", "payment_terms": "Net 30 days from invoice", "data_sensitivity": "Confidential",
                "security_review_required": True, "website": "https://www.heliodesk.example",
                "contact_phone": "+44 20 7946 0281", "headquarters": "London, United Kingdom",
                "implementation_notes": "Two-week configuration period before contract start.",
            }, "conflicts": []}
        if "RoutePilot" in prompt:
            return {"record": {
                "vendor_name": "RoutePilot", "legal_name": "RoutePilot Systems Inc.",
                "primary_contact_name": "Miguel Santos", "primary_contact_email": "miguel.santos@routepilot.example",
                "service_category": "SaaS spend and renewal analytics platform", "internal_owner_department": "Finance",
                "annual_cost_usd": 18600, "contract_start_date": "2026-11-15", "contract_end_date": "2027-11-14",
                "renewal_type": "automatic", "payment_terms": None, "data_sensitivity": "Internal",
                "security_review_required": False,
            }, "conflicts": []}
        if "CipherNest" in prompt:
            return {"record": {
                "vendor_name": "CipherNest", "legal_name": None, "primary_contact_name": "Nora Fischer",
                "primary_contact_email": "nora.fischer@ciphernest.example",
                "service_category": "Secure managed file-transfer software", "internal_owner_department": "IT",
                "annual_cost_usd": 31200, "contract_start_date": "2026-12-01", "contract_end_date": "2027-11-30",
                "renewal_type": "manual", "payment_terms": "Net 45 days", "data_sensitivity": "Restricted",
                "security_review_required": None, "contact_phone": "+49 30 5557 0184",
                "implementation_notes": "Three-week technical setup.",
            }, "conflicts": []}
        raise ValueError(
            "Deterministic vendor mode supports only the supplied HelioDesk, RoutePilot, and CipherNest fixtures. "
            "Set NOVAOPS_ANSWER_MODE=bedrock for arbitrary documents."
        )


def build_vendor_extractor_from_env() -> VendorExtractor:
    mode = os.getenv("NOVAOPS_ANSWER_MODE", "deterministic").strip().lower()
    if mode == "bedrock":
        return VendorExtractor(BedrockModelClient())
    if mode == "deterministic":
        return VendorExtractor(DeterministicVendorModel())
    raise ValueError("NOVAOPS_ANSWER_MODE must be 'deterministic' or 'bedrock'.")
