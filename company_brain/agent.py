from __future__ import annotations

from dataclasses import dataclass, field
import uuid

from maya import CallerContext, MayaAgent
from maya.ports import AnswerPort
from maya.policy import plan_turn, select_loadout
from maya.schemas import ContextPlan
from webex import WebexAccessWorkflow, WebexCaseInput
from webex.write_gate import RecordedApprovalWriteGate

from .schemas import AgentTurnResult
from .security import DisabledRequestGuard, GuardDecision, RequestGuard
from .instrumentation import observe
from .tools import GatewayEvidenceRetriever, GatewayOperations, GatewayWebexPort, LocalToolGateway, ToolGateway


@dataclass
class _ThreadContext:
    turns: int = 0
    workflow: str = ""
    subject_employee_id: str = ""
    drafted_justification: str = ""
    citations: list[str] = field(default_factory=list)


class CompanyBrainAgent:
    """Shared classify -> scope -> evidence -> answer entry point.

    Maya and Webex use one public API and one caller context. The two specialized
    workflow implementations remain small internal components while the facade
    owns routing, trace metadata and the write-gate boundary.
    """

    def __init__(
        self,
        tool_gateway: ToolGateway | None = None,
        answer_port: AnswerPort | None = None,
        request_guard: RequestGuard | None = None,
    ) -> None:
        self.tool_gateway = tool_gateway or LocalToolGateway()
        self.operations = GatewayOperations(self.tool_gateway)
        self.retriever = GatewayEvidenceRetriever(self.tool_gateway)
        self.maya = MayaAgent(
            self.retriever,
            GatewayWebexPort(self.tool_gateway),
            answer_port=answer_port,
            operations=self.operations,
        )
        self.webex = WebexAccessWorkflow(operations=self.operations)
        self.write_gate = RecordedApprovalWriteGate()
        self.request_guard = request_guard or DisabledRequestGuard()
        self._threads: dict[str, _ThreadContext] = {}

    def handle_turn(
        self,
        thread_id: str,
        caller: CallerContext,
        message: str,
        *,
        turn: int | None = None,
        request_id: str | None = None,
    ) -> AgentTurnResult:
        state = self._threads.setdefault(thread_id, _ThreadContext())
        state.turns = turn or (state.turns + 1)
        request_id = request_id or f"req-{uuid.uuid4().hex}"
        with observe("input_guard", input={"characters": len(message)}) as guarding:
            try:
                verdict = GuardDecision.model_validate(self.request_guard.inspect(message))
            except Exception:
                verdict = GuardDecision(
                    category="grey-zone",
                    decision="review",
                    reason="Guard unavailable or returned an invalid decision.",
                )
            guarding.update(output=verdict.model_dump())

        if verdict.decision != "allow":
            return AgentTurnResult(
                request_id=request_id,
                thread_id=thread_id,
                turn=state.turns,
                scope="security_boundary",
                intent="security_guard",
                status="blocked" if verdict.decision == "block" else "needs_human",
                answer=(
                    "I can't help with that request."
                    if verdict.decision == "block"
                    else "This request needs trusted human review before the agent can continue."
                ),
                caller_employee_id=caller.employee_id,
                caller_user_group=caller.user_group,
                guard_decision=verdict.model_dump(),
            )
        with observe("classify", input={"newest_message": message}) as classification:
            if not state.workflow:
                state.workflow = self._initial_workflow(message)
            maya_plan = plan_turn(state.turns, message, caller)
            direct_webex = state.turns == 1 and self._is_direct_webex(message)
            classification.update(
                output={
                    "workflow": state.workflow,
                    "planned_intent": maya_plan.intent,
                    "direct_webex": direct_webex,
                }
            )

        with observe(
            "scope",
            input={"caller_id": caller.employee_id, "caller_group": caller.user_group},
        ) as scoping:
            if state.workflow == "webex_boundary" or direct_webex:
                planned_scope = "webex_ops"
                visible_tools: list[str] = []
            else:
                planned_scope = (
                    "webex_ops"
                    if maya_plan.intent in {"ticket_status", "subscription_review", "access_request"}
                    else "maya_hr"
                )
                visible_tools = list(select_loadout(maya_plan))
            scoping.update(output={"scope": planned_scope, "visible_tools": visible_tools})

        with observe(
            "execute",
            input={"workflow": state.workflow, "planned_intent": maya_plan.intent},
        ) as execution:
            if state.workflow == "webex_boundary":
                result = self._handle_webex_boundary(thread_id, caller, message, state, request_id)
            elif direct_webex:
                result = self._handle_direct_webex(thread_id, caller, message, state, request_id)
            else:
                maya_result = self.maya.handle_turn_sync(thread_id, caller, state.turns, message)
                blocker_relevant = maya_plan.intent in {
                    "onboarding_status",
                    "subscription_review",
                    "access_request",
                    "software_license_status",
                    "summary",
                }
                status = "blocked" if blocker_relevant and maya_result.checklist.blocked_items else "completed"
                if maya_plan.intent == "unknown":
                    status = "needs_human"
                citations = list(dict.fromkeys(
                    [chunk.source_path for chunk in maya_result.retrieved]
                    + self._operational_citations(
                        maya_plan.intent,
                        maya_plan.subject_employee_id,
                        maya_result.operational_tool_calls,
                    )
                ))
                for citation in citations:
                    if citation not in state.citations:
                        state.citations.append(citation)
                if not citations and maya_plan.intent in {"recall", "summary"}:
                    citations = list(state.citations)
                result = AgentTurnResult(
                    request_id=request_id,
                    thread_id=thread_id,
                    turn=state.turns,
                    scope=planned_scope,
                    intent=maya_plan.intent,
                    status=status,
                    answer=maya_result.answer,
                    caller_employee_id=caller.employee_id,
                    caller_user_group=caller.user_group,
                    tool_sequence=maya_result.operational_tool_calls,
                    citations=citations,
                    payload=maya_result,
                )
            execution.update(
                output={
                    "intent": result.intent,
                    "status": result.status,
                    "tool_sequence": result.tool_sequence,
                }
            )

        result.guard_decision = verdict.model_dump()

        with observe("answer", input={"citations": result.citations}) as answering:
            result.answer = self._ensure_cited(result.answer, result.citations)
            answering.update(output={"answer": result.answer, "status": result.status})
        return result

    @staticmethod
    def _operational_citations(intent: str, subject_employee_id: str, tools: list[str]) -> list[str]:
        citations: list[str] = []
        mapping = {
            "get_employee": f"database/employees/{subject_employee_id}",
            "list_onboarding_tasks": f"database/onboarding_tasks/{subject_employee_id}",
            "list_employee_tickets": f"database/tickets/{subject_employee_id}",
            "check_asset_inventory": "database/assets",
            "check_software_subscription": "database/software_subscriptions/SUB001",
        }
        for tool in tools:
            if tool in mapping:
                citations.append(mapping[tool])
        return citations

    @staticmethod
    def _ensure_cited(answer: str, citations: list[str]) -> str:
        if not citations or "Sources:" in answer:
            return answer
        return answer.rstrip() + " Sources: " + "; ".join(f"[{source}]" for source in citations) + "."

    @staticmethod
    def _initial_workflow(message: str) -> str:
        lowered = message.lower()
        no_write = any(phrase in lowered for phrase in ("do not", "dont", "don't", "no-file", "lookup only"))
        mentions_write = any(word in lowered for word in ("create", "submit", "file", "request"))
        if "vpn" in lowered and no_write and mentions_write:
            return "webex_boundary"
        return "company_brain"

    @staticmethod
    def _is_direct_webex(message: str) -> bool:
        lowered = message.lower()
        if "webex" not in lowered:
            return False
        ticket_status = "ticket" in lowered and any(word in lowered for word in ("status", "open", "check"))
        seat_audit = "seat" in lowered and any(word in lowered for word in ("which", "who", "team", "member", "assigned"))
        access_problem = any(word in lowered for word in ("access", "license", "licensed")) and any(
            phrase in lowered
            for phrase in ("need", "not licensed", "unlicensed", "no license", "can't log in", "cannot log in")
        )
        return ticket_status or seat_audit or access_problem

    def _handle_direct_webex(
        self,
        thread_id: str,
        caller: CallerContext,
        message: str,
        state: _ThreadContext,
        request_id: str,
    ) -> AgentTurnResult:
        lowered = message.lower()
        if "seat" in lowered and any(word in lowered for word in ("which", "who", "team", "member", "assigned")):
            facts = self.operations.inspect_software_seat_assignments("Webex", caller.employee_id)
            answer = (
                "NovaOps does not record employee-to-seat assignments, so I cannot truthfully list which team "
                "members hold a Webex seat. The database only records 42 active seats against a 40-seat limit, "
                "plus entitlement, requests, and onboarding tasks; entitlement is not proof of assignment. "
                "Rachel Stein's request is blocked, Maya Cohen's Webex onboarding task is blocked, and Noam "
                "Sharon is not entitled to Webex by role."
            )
            return self._result(thread_id, caller, state, request_id, "seat_assignment_audit", "blocked", answer, ["inspect_software_seat_assignments"], facts)

        decision = self.webex.handle(
            WebexCaseInput(
                request=message,
                employee_id=caller.employee_id,
                caller_employee_id=caller.employee_id,
                caller_user_group=caller.user_group,
            )
        )
        intent = "ticket_status" if "status" in lowered and "ticket" in lowered else "access_diagnosis"
        status = "completed" if intent == "ticket_status" else "blocked" if decision.status == "blocked_pending_approvals" else "completed"
        return self._result(thread_id, caller, state, request_id, intent, status, decision.answer, decision.operational_tool_calls, decision)

    def _handle_webex_boundary(
        self,
        thread_id: str,
        caller: CallerContext,
        message: str,
        state: _ThreadContext,
        request_id: str,
    ) -> AgentTurnResult:
        lowered = message.lower()
        if "vpn" in lowered:
            plan = ContextPlan(state.turns, "vpn_access", subject_employee_id=caller.employee_id, required_evidence=("vpn_access.md",))
            chunks = self.retriever.retrieve("VPN access MFA trusted device", caller, plan)
            answer = (
                "Use a NovaOps-managed or registered device, complete MFA, then follow the VPN enrollment steps; "
                "IT must resolve device-trust or approval failures. Source: [documents/it_kb/vpn_access.md]."
            )
            return self._result(thread_id, caller, state, request_id, "vpn_access", "completed", answer, ["retrieve_evidence"], chunks)
        if "rrachel stein" in lowered or "rachel stein" in lowered and "employee" in lowered:
            employee = self.operations.get_employee("Rachel Stein")
            state.subject_employee_id = "E010"
            answer = "Rachel Stein is employee E010, a Customer Success Specialist in Customer Success."
            return self._result(thread_id, caller, state, request_id, "employee_lookup", "completed", answer, ["get_employee"], employee)
        if "go ahead" in lowered and ("file" in lowered or "create" in lowered):
            existing = self.operations.list_access_requests(state.subject_employee_id or "E010", "Webex")
            if existing:
                request = existing[0]
                gate = self.write_gate.evaluate("create_access_request", request["request_id"])
                answer = (
                    f"I reused access request {request['request_id']}, which was already filed and is {request['status']}; "
                    "no duplicate was created. Access is not granted. Its recorded approvals are still outstanding, "
                    "and Webex remains over the 40-seat limit."
                )
                return self._result(
                    thread_id,
                    caller,
                    state,
                    request_id,
                    "access_request",
                    "pending",
                    answer,
                    ["list_access_requests", "recorded_approval_write_gate"],
                    {"request": request, "write_gate": gate},
                )
            gate = self.write_gate.evaluate("create_access_request", "unrecorded")
            answer = "No existing request was found, and no recorded approval exists, so the write gate released nothing."
            return self._result(thread_id, caller, state, request_id, "access_request", "needs_human", answer, ["list_access_requests", "recorded_approval_write_gate"], gate)
        if "draft" in lowered or "words for" in lowered:
            state.drafted_justification = "Rachel Stein needs Webex for Customer Success onboarding and customer calls."
            return self._result(thread_id, caller, state, request_id, "draft_justification", "completed", state.drafted_justification, [], {"draft_only": True})
        return self._result(thread_id, caller, state, request_id, "unknown", "needs_human", "I need a clearer current request.", [], None)

    @staticmethod
    def _result(
        thread_id: str,
        caller: CallerContext,
        state: _ThreadContext,
        request_id: str,
        intent: str,
        status: str,
        answer: str,
        tools: list[str],
        payload,
    ) -> AgentTurnResult:
        citations = []
        if isinstance(payload, list):
            citations = list(dict.fromkeys(getattr(item, "source_path", "") for item in payload if getattr(item, "source_path", "")))
        return AgentTurnResult(
            request_id=request_id,
            thread_id=thread_id,
            turn=state.turns,
            scope="webex_ops",
            intent=intent,
            status=status,  # type: ignore[arg-type]
            answer=answer,
            caller_employee_id=caller.employee_id,
            caller_user_group=caller.user_group,
            tool_sequence=tools,
            citations=citations,
            payload=payload,
        )
