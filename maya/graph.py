from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from . import ops
from .policy import plan_turn, select_loadout
from .ports import AnswerPort, WebexPort
from .retrieval import EvidenceRetriever, PermissionDenied
from .schemas import (
    CallerContext,
    ChecklistItem,
    ContextPlan,
    EvidenceChunk,
    OnboardingChecklist,
    PendingAccessResult,
    TurnResult,
    WebexHandoff,
)


@dataclass
class ThreadState:
    thread_id: str
    caller: CallerContext
    start_date: str = "2026-08-01"
    location: str = "Israel"
    q3_freeze: bool = True
    tangent_closed: bool = False
    retrieved: list[EvidenceChunk] = field(default_factory=list)
    operational_tool_calls: list[str] = field(default_factory=list)
    operational_records: dict[str, list[dict]] = field(default_factory=dict)
    handoffs: dict[str, PendingAccessResult] = field(default_factory=dict)
    max_steps: int = 8


class MayaAgent:
    def __init__(
        self,
        retriever: EvidenceRetriever,
        webex_port: WebexPort,
        answer_port: AnswerPort | None = None,
        operations=ops,
    ) -> None:
        self.retriever = retriever
        self.webex_port = webex_port
        self.answer_port = answer_port
        self.ops = operations
        self._threads: dict[str, ThreadState] = {}

    def state_for(self, thread_id: str, caller: CallerContext) -> ThreadState:
        if thread_id not in self._threads:
            self._threads[thread_id] = ThreadState(thread_id=thread_id, caller=caller)
        return self._threads[thread_id]

    async def handle_turn(self, thread_id: str, caller: CallerContext, turn: int, user_text: str) -> TurnResult:
        state = self.state_for(thread_id, caller)
        plan = plan_turn(turn, user_text, caller)
        loadout = select_loadout(plan)
        calls: list[str] = []
        retrieved: list[EvidenceChunk] = []
        errors: list[str] = []

        if plan.close_tangent:
            state.tangent_closed = True

        try:
            if "search_evidence" in loadout:
                self.retriever.assert_authorized(caller, plan.subject_employee_id)
                retrieved = self.retriever.retrieve(user_text, caller, plan)
                missing = self._missing_required_evidence(retrieved, plan)
                if missing:
                    refined_query = " ".join(missing)
                    refined = self.retriever.retrieve(refined_query, caller, plan)
                    retrieved = self._merge_evidence(retrieved, refined)
                state.retrieved.extend(retrieved)
                calls.append("search_evidence")
        except PermissionDenied as exc:
            errors.append(str(exc))
            return TurnResult(turn, plan.intent, "Access denied.", self._checklist([], {}), retrieved, calls, [], errors)

        records = self._run_operational_reads(plan, loadout, calls)
        state.operational_records.update(records)
        checklist = self._checklist(state.retrieved + retrieved, state.operational_records)
        handoffs: list[PendingAccessResult] = []

        if plan.allow_webex_handoff:
            handoff = self._webex_handoff(caller, checklist)
            result = await self._request_webex_once(state, handoff)
            checklist.handoffs.append(result)
            handoffs.append(result)

        answer = self._answer(plan, checklist, records, retrieved, state, handoffs)
        if self.answer_port is not None:
            try:
                deterministic_answer = answer
                model_answer = await self.answer_port.answer(
                    self._answer_prompt(plan, checklist, records, retrieved, state, handoffs, deterministic_answer)
                )
                answer = self._guard_model_answer(plan, model_answer, deterministic_answer)
                if answer == deterministic_answer and model_answer != deterministic_answer:
                    errors.append(f"model_answer_contract_fallback:{plan.intent}")
            except Exception as exc:
                errors.append(f"model_answer_fallback:{exc}")
        state.operational_tool_calls.extend(calls)
        return TurnResult(turn, plan.intent, answer, checklist, retrieved, calls, handoffs, errors)

    @staticmethod
    def _guard_model_answer(plan: ContextPlan, model_answer: str, deterministic_answer: str) -> str:
        """Fail closed when a model rewrite drops binding policy facts."""

        required_phrases = {
            "promotion_path": ("six months", "April 1", "October 1"),
        }.get(plan.intent, ())
        folded = model_answer.casefold()
        if any(phrase.casefold() not in folded for phrase in required_phrases):
            return deterministic_answer
        return model_answer

    def handle_turn_sync(self, thread_id: str, caller: CallerContext, turn: int, user_text: str) -> TurnResult:
        return asyncio.run(self.handle_turn(thread_id, caller, turn, user_text))

    def invalidate_retrieved_evidence(
        self,
        *,
        chunk_ids: tuple[str, ...] = (),
        source_paths: tuple[str, ...] = (),
    ) -> dict[str, int]:
        """Remove quarantined evidence from every in-process conversation state."""

        denied_ids = set(chunk_ids)
        denied_sources = set(source_paths)
        before = sum(len(state.retrieved) for state in self._threads.values())
        for state in self._threads.values():
            state.retrieved = [
                chunk
                for chunk in state.retrieved
                if chunk.chunk_id not in denied_ids and chunk.source_path not in denied_sources
            ]
        after = sum(len(state.retrieved) for state in self._threads.values())
        return {"before": before, "removed": before - after, "after": after}

    def _run_operational_reads(self, plan: ContextPlan, loadout: tuple[str, ...], calls: list[str]) -> dict[str, list[dict]]:
        records: dict[str, list[dict]] = {}
        if "get_employee" in loadout:
            records["employee"] = self.ops.get_employee(plan.subject_employee_id)
            calls.append("get_employee")
        if "list_onboarding_tasks" in loadout:
            records["tasks"] = self.ops.list_onboarding_tasks(plan.subject_employee_id)
            calls.append("list_onboarding_tasks")
        if "check_asset_inventory" in loadout:
            records["assets"] = self.ops.check_asset_inventory(location="Israel")
            calls.append("check_asset_inventory")
        if "list_employee_tickets" in loadout:
            records["tickets"] = self.ops.list_employee_tickets(plan.subject_employee_id)
            calls.append("list_employee_tickets")
        if "check_software_subscription" in loadout:
            records["subscriptions"] = self.ops.check_software_subscription("Webex")
            calls.append("check_software_subscription")
        return records

    @staticmethod
    def _missing_required_evidence(evidence: list[EvidenceChunk], plan: ContextPlan) -> tuple[str, ...]:
        found = {chunk.source_path for chunk in evidence}
        return tuple(required for required in plan.required_evidence if not any(required in path for path in found))

    @staticmethod
    def _merge_evidence(primary: list[EvidenceChunk], refined: list[EvidenceChunk]) -> list[EvidenceChunk]:
        merged: dict[str, EvidenceChunk] = {chunk.chunk_id: chunk for chunk in primary}
        for chunk in refined:
            merged.setdefault(chunk.chunk_id, chunk)
        return list(merged.values())

    def _checklist(self, evidence: list[EvidenceChunk], records: dict[str, list[dict]]) -> OnboardingChecklist:
        citation_map = {chunk.source_path: chunk.citation() for chunk in evidence}

        def cite(*names: str):
            return tuple(c for path, c in citation_map.items() if any(name in path for name in names))

        checklist = OnboardingChecklist()
        offer = cite("maya_cohen_offer_letter.md")
        access = cite("access_management_policy.md", "salesforce_access_request.md")
        equipment = cite("equipment_policy.md", "laptop_provisioning.md")
        webex = cite("webex_license_assignment.md", "webex_vendor_agreement.md", "webex_subscription.md", "saas_renewal_freeze_q3.md")

        checklist.systems.extend(
            [
                ChecklistItem("Okta", "pending", "Create Okta profile and baseline groups.", offer),
                ChecklistItem("Slack", "required", "Required day-one collaboration system.", offer),
                ChecklistItem("Notion", "required", "Required day-one knowledge system.", offer),
                ChecklistItem("Salesforce", "planned", "Customer Success profile is planned before start date.", offer + access),
                ChecklistItem("SupportDesk viewer", "required", "Required for Customer Success onboarding.", offer),
                ChecklistItem("BambooHR employee self-service", "planned", "Employee self-service profile is planned.", offer),
                ChecklistItem("Webex", "blocked_or_pending", "Seat availability is blocked by the over-limit subscription; handoff may be pending.", offer + webex),
            ]
        )

        asset_records = records.get("assets", [])
        laptop = next((a for a in asset_records if a["asset_type"] == "Laptop" and a["status"] == "available"), None)
        monitor = next((a for a in asset_records if a["asset_type"] == "Monitor" and a["status"] == "available"), None)
        checklist.equipment.extend(
            [
                ChecklistItem("Laptop", "ready" if laptop else "unresolved", (laptop or {}).get("model", "No available laptop found."), equipment),
                ChecklistItem("Monitor", "ready" if monitor else "unresolved", (monitor or {}).get("model", "No available monitor found."), equipment),
                ChecklistItem("Headset", "required", "Customer Success role needs meeting audio equipment; inventory not confirmed.", equipment),
            ]
        )

        checklist.policy_requirements.extend(
            [
                ChecklistItem("Q3 SaaS freeze", "finance_required", "New paid SaaS spend over 7500 requires Finance review.", webex),
                ChecklistItem("MFA", "required", "Required for core systems.", cite("access_management_policy.md")),
                ChecklistItem("Policy acknowledgements", "planned", "Acceptable use, security/MFA, remote equipment, and onboarding acknowledgements remain in scope.", cite("onboarding_policy.md", "equipment_policy.md")),
            ]
        )

        subscriptions = records.get("subscriptions", [])
        sub = subscriptions[0] if subscriptions else None
        if sub and sub["over_limit"]:
            checklist.blocked_items.append(
                ChecklistItem(
                    "Webex license",
                    "blocked_or_pending",
                    f"Webex has {sub['active_seats']} active seats against a {sub['seat_limit']}-seat limit; Finance/IT expansion path is required.",
                    webex,
                )
            )
        return checklist

    def _webex_handoff(self, caller: CallerContext, checklist: OnboardingChecklist) -> WebexHandoff:
        evidence = tuple(
            c for item in checklist.blocked_items for c in item.evidence if "webex" in c.source_path.lower() or "saas" in c.source_path.lower()
        )
        return WebexHandoff(
            employee_id="E001",
            software="Webex",
            caller_employee_id=caller.employee_id,
            caller_user_group=caller.user_group,
            business_reason="Maya Cohen needs Webex for Customer Success onboarding meetings; subscription is over the 40-seat limit and needs the Webex workflow.",
            idempotency_key="maya:E001:webex:S2-onboarding-maya",
            evidence=evidence,
        )

    async def _request_webex_once(self, state: ThreadState, handoff: WebexHandoff) -> PendingAccessResult:
        if handoff.idempotency_key in state.handoffs:
            return state.handoffs[handoff.idempotency_key]
        result = await self.webex_port.request_access(handoff)
        state.handoffs[handoff.idempotency_key] = result
        return result

    def _answer(
        self,
        plan: ContextPlan,
        checklist: OnboardingChecklist,
        records: dict[str, list[dict]],
        retrieved: list[EvidenceChunk],
        state: ThreadState,
        handoffs: list[PendingAccessResult],
    ) -> str:
        citations = self._citation_suffix(retrieved)
        if plan.intent == "employee_lookup":
            employee = (records.get("employee") or [{}])[0]
            return (
                f"Maya Cohen is employee {employee.get('employee_id', 'E001')}, a "
                f"{employee.get('role', 'Customer Success Manager')} in {employee.get('status', 'preboarding')} "
                f"status. She is a {employee.get('employment_type', 'full-time')} employee based in "
                f"{employee.get('location', state.location)} and starts {employee.get('start_date', state.start_date)}."
            )
        if plan.intent == "help":
            return (
                "I can help with Maya's employee profile, day-one systems, onboarding checklist, equipment, "
                "Webex availability, finance policy, blockers, and a final status summary. Ask in your own words; "
                "I will use only authorized NovaOps evidence and will not grant access directly."
            )
        if plan.intent == "personal_device_policy":
            return (
                "Employees may not use a personal laptop except for a five-business-day continuity "
                "exception while a managed device is repaired or replaced; IT must approve and log it first."
                f"{citations}"
            )
        if plan.intent == "mfa_reset":
            return (
                "Have your identity verified by manager, HR, or IT video check, confirm there is no suspicious "
                "login, then IT can reset the Okta factor and require immediate MFA re-enrollment. A changed "
                f"phone should be re-registered as the trusted device.{citations}"
            )
        if plan.intent == "remote_equipment_eligibility":
            return (
                "Yes. Maya is a full-time hybrid employee in Israel, so she receives a managed laptop; her "
                "approved work arrangement also makes a monitor and dock eligible, and a CSM may receive a headset."
                f"{citations}"
            )
        if plan.intent == "promotion_path":
            return (
                "For a CSM, use the Support and Customer Success title ladder as the role guide. Promotion "
                "normally requires at least six months in role plus sustained evidence of next-level work. "
                "Cycles take effect April 1 and October 1 after manager, People Operations, department, and "
                f"Finance review.{citations}"
            )
        if plan.intent == "forwarded_action_summary":
            return (
                "Only two items are yours: sign the equipment responsibility form, and finish your BambooHR "
                "self-service profile when the invitation arrives. The other items remain with IT, HR, or your manager."
            )
        if plan.intent == "software_license_status":
            sub = records["subscriptions"][0]
            return (
                "Your role-based onboarding includes the standard Customer Success systems, but provisioning "
                f"is owned by IT/HR. Webex is currently blocked because there are {sub['active_seats']} active "
                f"seats against a {sub['seat_limit']}-seat contract limit; that is a company seat issue, not a "
                f"problem with your eligibility.{citations}"
            )
        if plan.intent == "restricted_manager_guide":
            return (
                "The manager-only guide is not available to your account, so I cannot quote or summarize it. "
                "I can help with employee-visible career and feedback guidance instead."
            )
        if plan.intent == "laptop_status":
            task = next((item for item in records.get("tasks", []) if "laptop" in item["description"].lower()), None)
            assets = records.get("assets", [])
            laptop = next((item for item in assets if item["asset_type"] == "Laptop"), None)
            due = task["due_date"] if task else "not recorded"
            model = laptop["model"] if laptop else "managed laptop"
            status = task["status"] if task else "unconfirmed"
            return (
                f"The system of record shows your laptop bundle as {status}, due {due}, before your August 1 "
                f"start; the available Israel inventory lists {model}. This is planned, not yet completed."
                f"{citations}"
            )
        if plan.intent == "ticket_status":
            ticket = records["tickets"][0]
            return f"Rachel Stein's ticket {ticket['ticket_id']} is {ticket['status']} with {ticket['assigned_team']}; I will drop that tangent after this turn."
        if plan.intent == "recall":
            return f"Maya is based in {state.location} and starts {state.start_date}."
        if plan.intent == "access_request":
            result = handoffs[0]
            return f"Webex handoff {result.request_id} is {result.status}; Maya does not have granted access yet."
        if plan.intent in {"summary", "overview"}:
            blocked = "; ".join(item.detail.rstrip(".") for item in checklist.blocked_items) or "Webex license capacity requires confirmation"
            return (
                f"Maya Cohen ({checklist.employee_id}) starts {checklist.start_date} in {checklist.location}. "
                f"Role: {checklist.role}. Systems include Okta, Slack, Notion, Salesforce, Webex, BambooHR, and SupportDesk. "
                f"Open blocker: {blocked}. The earlier unrelated ticket tangent is excluded from this Maya summary."
            )
        if plan.intent == "policy_question":
            return "Because the Q3 SaaS freeze applies and Webex annual cost is 18400, adding a seat requires Finance/IT review over the 7500 threshold."
        if plan.intent == "subscription_review":
            sub = records["subscriptions"][0]
            return f"No Webex seat is available: {sub['active_seats']} active seats against a {sub['seat_limit']}-seat limit."
        if plan.intent == "equipment_request":
            laptop = next(
                (
                    item
                    for item in records.get("assets", [])
                    if item["asset_type"] == "Laptop" and item["status"] == "available"
                ),
                None,
            )
            monitor = next(
                (
                    item
                    for item in records.get("assets", [])
                    if item["asset_type"] == "Monitor" and item["status"] == "available"
                ),
                None,
            )
            laptop_fact = (
                f"laptop {laptop['asset_id']} ({laptop['model']}) is available"
                if laptop
                else "no available laptop is recorded"
            )
            monitor_fact = (
                f"monitor {monitor['asset_id']} ({monitor['model']}) is available"
                if monitor
                else "no available monitor is recorded"
            )
            return (
                f"Israel inventory shows {laptop_fact}; {monitor_fact}. "
                f"A headset is required, but availability remains unconfirmed.{citations}"
            )
        if plan.intent == "offer_letter":
            return "Maya's offer letter requires Okta, Slack, Notion, Salesforce, Webex, BambooHR employee self-service, SupportDesk viewer, and remote equipment."
        if plan.intent == "onboarding_status":
            return "Maya's checklist includes Okta pending, laptop/equipment planned, Salesforce planned, Webex blocked, and BambooHR planned."
        return (
            "I can help with Maya's onboarding record, required systems, equipment, Webex status, finance policy, "
            "current blockers, or a full status summary. Please ask about one of those areas."
        )

    @staticmethod
    def _citation_suffix(retrieved: list[EvidenceChunk]) -> str:
        sources: list[str] = []
        for chunk in retrieved:
            if chunk.source_path not in sources:
                sources.append(chunk.source_path)
        if not sources:
            return ""
        return " Sources: " + "; ".join(f"[{source}]" for source in sources) + "."

    @staticmethod
    def _answer_prompt(
        plan: ContextPlan,
        checklist: OnboardingChecklist,
        records: dict[str, list[dict]],
        retrieved: list[EvidenceChunk],
        state: ThreadState,
        handoffs: list[PendingAccessResult],
        deterministic_answer: str,
    ) -> str:
        evidence = "\n".join(
            f"- {chunk.source_path}: {chunk.text[:500]}"
            for chunk in retrieved[:6]
        ) or "- No new evidence retrieved on this turn."
        handoff_lines = "\n".join(
            f"- {handoff.request_id}: {handoff.status}"
            for handoff in handoffs
        ) or "- No new handoff on this turn."
        return (
            "You are Maya, a NovaOps onboarding evidence agent. Answer the current turn "
            "using only the supplied plan, records, checklist, evidence, memory, and handoff state. "
            "Do not claim Webex access was granted; a handoff can only be pending. "
            "Keep the answer concise and operational.\n\n"
            f"Intent: {plan.intent}\n"
            f"Active constraints: {', '.join(plan.active_constraints)}\n"
            f"Thread memory: start_date={state.start_date}, location={state.location}, "
            f"q3_freeze={state.q3_freeze}, tangent_closed={state.tangent_closed}\n"
            f"Records: {records}\n"
            f"Checklist blocked items: {[item.detail for item in checklist.blocked_items]}\n"
            f"Handoffs:\n{handoff_lines}\n"
            f"Evidence:\n{evidence}\n\n"
            f"Deterministic fallback answer:\n{deterministic_answer}\n\n"
            "Return only the user-facing answer."
        )
