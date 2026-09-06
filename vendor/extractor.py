from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, Protocol

from jsonschema import Draft202012Validator, FormatChecker

from company_brain.instrumentation import observe
from model_client import BedrockModelClient


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    ROOT
    / "novaops-enterprise-agent-dataset"
    / "workflows"
    / "vendor"
    / "schemas"
    / "vendor_extraction_result.schema.json"
)


class StructuredModel(Protocol):
    model_id: str

    def extract_with_tool(
        self,
        prompt: str,
        *,
        tool_name: str,
        input_schema: dict[str, Any],
        system: str = "",
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class VendorExtractionResult:
    source_id: str
    source_type: str
    record: dict[str, Any]
    missing_required_fields: list[str]
    conflicts: list[str]
    follow_up_questions: list[dict[str, str]]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class VendorExtractor:
    """Standalone one-call vendor CRM extractor with deterministic validation."""

    def __init__(self, model: StructuredModel | None = None, schema_path: Path = SCHEMA_PATH) -> None:
        self.model = model or BedrockModelClient()
        self.schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.validator = Draft202012Validator(self.schema, format_checker=FormatChecker())
        record_schema = self.schema["$defs"]["vendor_crm_record"]
        self.record_fields = tuple(record_schema["properties"])
        self.required_crm_fields = tuple(
            name
            for name, definition in record_schema["properties"].items()
            if definition.get("x-crm-required") is True
        )

    def extract(self, source_id: str, source_type: str, document: str) -> VendorExtractionResult:
        if source_type not in {"formal_document", "email_chain", "call_transcript"}:
            raise ValueError(f"Unsupported source_type: {source_type}")
        prompt = self._prompt(source_id, source_type, document)
        with observe(
            "bedrock_vendor_extraction",
            as_type="generation",
            input={"source_id": source_id, "source_type": source_type, "document": document},
            model=self.model.model_id,
            model_parameters={"tool_choice": "submit_vendor_record"},
        ) as generation:
            raw = self.model.extract_with_tool(
                prompt,
                tool_name="submit_vendor_record",
                input_schema=self.schema,
                system=(
                    "Extract only explicitly stated facts. Do not infer missing fields. "
                    "Ignore details outside the supplied schema and use null for unstated values."
                ),
            )
            generation.update(output=raw, metadata={"completed": True})
        with observe("vendor_normalize_and_validate", input=raw) as validation:
            normalized = self._normalize(raw, source_id=source_id, source_type=source_type)
            errors = sorted(self.validator.iter_errors(normalized), key=lambda error: list(error.path))
            if errors:
                details = "; ".join(f"{'/'.join(map(str, error.path)) or '<root>'}: {error.message}" for error in errors)
                validation.update(output={"valid": False, "errors": details})
                raise ValueError(f"Vendor extraction failed schema validation: {details}")
            validation.update(
                output={"valid": True, "missing_required_fields": normalized["missing_required_fields"]}
            )
        return VendorExtractionResult(**normalized)

    def _normalize(self, raw: dict[str, Any], *, source_id: str, source_type: str) -> dict[str, Any]:
        record_raw = raw.get("record") if isinstance(raw.get("record"), dict) else {}
        record = {field: record_raw.get(field) for field in self.record_fields}
        record["annual_cost_usd"] = self._integer(record["annual_cost_usd"])
        record["contract_start_date"] = self._date(record["contract_start_date"])
        record["contract_end_date"] = self._date(record["contract_end_date"])
        if isinstance(record["renewal_type"], str):
            renewal = record["renewal_type"].strip().casefold().replace(" renewal", "")
            record["renewal_type"] = {
                "auto": "automatic",
                "auto-renewal": "automatic",
                "automatic": "automatic",
                "manual": "manual",
                "usage-based": "usage_based",
                "usage based": "usage_based",
                "ambiguous": "ambiguous",
            }.get(renewal, renewal)
        if isinstance(record["data_sensitivity"], str):
            record["data_sensitivity"] = record["data_sensitivity"].strip().title()
        if isinstance(record["security_review_required"], str):
            folded = record["security_review_required"].strip().casefold()
            record["security_review_required"] = True if folded in {"yes", "true", "required"} else False if folded in {"no", "false", "not required"} else None

        missing = [field for field in self.required_crm_fields if record[field] is None]
        conflicts = [str(item).strip() for item in raw.get("conflicts", []) if str(item).strip()]
        follow_ups = [
            {"field": field, "question": self._follow_up(field)}
            for field in missing
        ]
        return {
            "source_id": source_id,
            "source_type": source_type,
            "record": record,
            "missing_required_fields": missing,
            "conflicts": conflicts,
            "follow_up_questions": follow_ups,
        }

    @staticmethod
    def _integer(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        digits = re.sub(r"[^0-9]", "", str(value))
        return int(digits) if digits else None

    @staticmethod
    def _date(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        for format_string in ("%Y-%m-%d", "%B %d, %Y", "%d %B %Y", "%b %d, %Y", "%d %b %Y"):
            try:
                return datetime.strptime(text, format_string).date().isoformat()
            except ValueError:
                continue
        return text

    @staticmethod
    def _follow_up(field: str) -> str:
        labels = {
            "legal_name": "What is the vendor's registered legal company name?",
            "payment_terms": "What invoice payment terms apply to this contract?",
            "security_review_required": "Does NovaOps require a security review for this engagement?",
        }
        return labels.get(field, f"What is the confirmed value for {field.replace('_', ' ')}?")

    @staticmethod
    def _prompt(source_id: str, source_type: str, document: str) -> str:
        return (
            f"Source id: {source_id}\nSource type: {source_type}\n\n"
            "Extract a vendor CRM record from the document below. Include every schema key, use null "
            "for unstated fields, report only absent required CRM fields, and ignore unrelated details.\n\n"
            f"DOCUMENT\n{document}"
        )


def extract_vendor(source_id: str, source_type: str, document: str) -> VendorExtractionResult:
    return VendorExtractor().extract(source_id, source_type, document)
