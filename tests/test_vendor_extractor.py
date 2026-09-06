from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from vendor import VendorExtractor


ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = ROOT / "novaops-enterprise-agent-dataset" / "workflows" / "vendor"


class FakeStructuredModel:
    model_id = "fake-structured-model"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def extract_with_tool(self, prompt: str, **kwargs) -> dict:
        self.calls.append({"prompt": prompt, **kwargs})
        if "formal_vendor_intake" in prompt:
            return _raw_record(
                vendor_name="HelioDesk",
                legal_name="HelioDesk Technologies Ltd.",
                primary_contact_name="Ava Patel",
                primary_contact_email="ava.patel@heliodesk.example",
                service_category="Customer support quality assurance SaaS",
                internal_owner_department="Customer Success",
                annual_cost_usd="USD 28,800",
                contract_start_date="October 1, 2026",
                contract_end_date="September 30, 2027",
                renewal_type="Manual renewal",
                payment_terms="Net 30 days from invoice",
                data_sensitivity="confidential",
                security_review_required="Yes",
                website="https://www.heliodesk.example",
                contact_phone="+44 20 7946 0281",
                headquarters="London, United Kingdom",
                implementation_notes="Two-week configuration period.",
            )
        if "procurement_email_chain" in prompt:
            return _raw_record(
                vendor_name="RoutePilot",
                legal_name="RoutePilot Systems Inc.",
                primary_contact_name="Miguel Santos",
                primary_contact_email="miguel.santos@routepilot.example",
                service_category="SaaS spend and renewal analytics platform",
                internal_owner_department="Finance",
                annual_cost_usd=18600,
                contract_start_date="2026-11-15",
                contract_end_date="2027-11-14",
                renewal_type="automatic",
                payment_terms=None,
                data_sensitivity="Internal",
                security_review_required=False,
            )
        return _raw_record(
            vendor_name="CipherNest",
            legal_name=None,
            primary_contact_name="Nora Fischer",
            primary_contact_email="nora.fischer@ciphernest.example",
            service_category="Secure managed file-transfer software",
            internal_owner_department="IT",
            annual_cost_usd=31200,
            contract_start_date="2026-12-01",
            contract_end_date="2027-11-30",
            renewal_type="manual",
            payment_terms="Net 45 days",
            data_sensitivity="Restricted",
            security_review_required=None,
            contact_phone="+49 30 5557 0184",
            implementation_notes="Three-week technical setup.",
        )


def _raw_record(**values) -> dict:
    return {"record": values, "conflicts": []}


def test_vendor_sources_are_schema_valid_with_zero_one_two_required_gaps() -> None:
    model = FakeStructuredModel()
    extractor = VendorExtractor(model=model)
    cases = [
        ("formal_vendor_intake", "formal_document", 0),
        ("procurement_email_chain", "email_chain", 1),
        ("discovery_call_transcript", "call_transcript", 2),
    ]
    schema = json.loads((VENDOR_ROOT / "schemas" / "vendor_extraction_result.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    for source_id, source_type, missing_count in cases:
        document = (VENDOR_ROOT / "sources" / f"{source_id}.md").read_text(encoding="utf-8")
        result = extractor.extract(source_id, source_type, document)
        validator.validate(result.as_dict())
        assert len(result.missing_required_fields) == missing_count
        assert len(result.follow_up_questions) == missing_count

    assert len(model.calls) == 3
    assert model.calls[0]["tool_name"] == "submit_vendor_record"


def test_optional_omissions_do_not_create_follow_up_and_irrelevant_detail_is_excluded() -> None:
    result = VendorExtractor(model=FakeStructuredModel()).extract(
        "procurement_email_chain",
        "email_chain",
        (VENDOR_ROOT / "sources" / "procurement_email_chain.md").read_text(encoding="utf-8"),
    )

    assert result.missing_required_fields == ["payment_terms"]
    assert result.record["website"] is None
    assert result.record["headquarters"] is None
    serialized = json.dumps(result.as_dict())
    assert "marathon" not in serialized
    assert "blue theme" not in serialized
