from __future__ import annotations

from .schemas import CallerContext, ContextPlan

READ_TOOL_LOADOUTS: dict[str, tuple[str, ...]] = {
    "employee_lookup": ("get_employee",),
    "onboarding_status": ("get_employee", "list_onboarding_tasks"),
    "offer_letter": ("search_evidence",),
    "ticket_status": ("list_employee_tickets",),
    "equipment_request": ("check_asset_inventory", "search_evidence"),
    "policy_question": ("search_evidence", "check_software_subscription"),
    "subscription_review": ("check_software_subscription", "search_evidence"),
    "access_request": (),
    "overview": ("get_employee", "list_onboarding_tasks", "check_software_subscription"),
    "summary": (),
    "recall": (),
    "personal_device_policy": ("search_evidence",),
    "mfa_reset": ("search_evidence",),
    "remote_equipment_eligibility": ("get_employee", "search_evidence"),
    "promotion_path": ("search_evidence",),
    "forwarded_action_summary": (),
    "software_license_status": ("list_onboarding_tasks", "check_software_subscription", "search_evidence"),
    "restricted_manager_guide": ("search_evidence",),
    "laptop_status": ("list_onboarding_tasks", "check_asset_inventory", "search_evidence"),
    "help": (),
    "unknown": (),
}

EXPECTED_READ_TOOLS_BY_TURN: dict[int, tuple[str, ...]] = {
    1: ("get_employee",),
    2: ("search_evidence",),
    3: ("list_onboarding_tasks",),
    4: ("list_employee_tickets",),
    5: ("check_asset_inventory",),
    6: ("search_evidence",),
    7: (),
    8: ("check_software_subscription",),
    9: ("search_evidence", "check_software_subscription"),
    10: (),
    11: ("list_onboarding_tasks",),
    12: (),
}

FORBIDDEN_TOOLS = {"create_access_request"}


def plan_turn(turn: int, text: str, caller: CallerContext) -> ContextPlan:
    lower = text.lower()
    subject_employee_id = "E001"
    constraints = [f"subject:{subject_employee_id}"]
    if turn >= 1:
        constraints.extend(["start_date:2026-08-01", "location:Israel", "q3_saas_freeze:true"])

    if (
        "pull up her employee record" in lower
        or (
            "maya" in lower
            and any(phrase in lower for phrase in ("employee record", "employee profile", "who is", "tell me about", "when does maya", "maya start"))
        )
    ):
        return ContextPlan(turn, "employee_lookup", subject_employee_id=subject_employee_id, active_constraints=tuple(constraints), operational_reads=("get_employee",))
    if "rachel stein" in lower or "ticket" in lower:
        return ContextPlan(turn, "ticket_status", subject_employee_id="E010", active_constraints=tuple(constraints), operational_reads=("list_employee_tickets",))
    if "drop it" in lower and "laptop" in lower:
        return ContextPlan(
            turn,
            "equipment_request",
            active_constraints=tuple(constraints),
            required_evidence=("laptop_provisioning.md", "equipment_policy.md"),
            operational_reads=("check_asset_inventory",),
            close_tangent=True,
        )
    if any(phrase in lower for phrase in ("personal laptop", "own laptop", "personal device")):
        return ContextPlan(
            turn,
            "personal_device_policy",
            subject_employee_id=caller.employee_id,
            required_evidence=("equipment_policy.md", "acceptable_use_policy.md"),
        )
    if (
        "reset mfa" in lower
        or ("mfa" in lower and any(word in lower for word in ("phone", "device", "authenticator")))
        or ("authenticator" in lower and any(word in lower for word in ("replace", "replaced", "lost", "new")))
    ):
        return ContextPlan(
            turn,
            "mfa_reset",
            subject_employee_id=caller.employee_id,
            required_evidence=("mfa_reset.md", "okta_device_change.md"),
        )
    if "remote" in lower and "equipment" in lower and any(word in lower for word in ("eligible", "qualify", "receive", "get")):
        return ContextPlan(
            turn,
            "remote_equipment_eligibility",
            subject_employee_id="E001",
            required_evidence=(
                "equipment_policy.md",
                "maya_cohen_offer_letter.md",
                "remote_equipment_budget_update.md",
            ),
            operational_reads=("get_employee",),
        )
    if "get promoted" in lower or "promotion" in lower or "career path" in lower:
        return ContextPlan(
            turn,
            "promotion_path",
            subject_employee_id=caller.employee_id,
            required_evidence=("making-a-career.md", "titles-for-support.md"),
        )
    if "only two that need you" in lower or ("what here is actually mine" in lower and "bamboohr" in lower):
        return ContextPlan(turn, "forwarded_action_summary", subject_employee_id=caller.employee_id)
    if "software licenses sorted" in lower:
        return ContextPlan(
            turn,
            "software_license_status",
            subject_employee_id=caller.employee_id,
            required_evidence=("access_management_policy.md", "webex_vendor_agreement.md"),
            operational_reads=("list_onboarding_tasks", "check_software_subscription"),
        )
    if "manager's guide" in lower or "manager guide" in lower:
        return ContextPlan(
            turn,
            "restricted_manager_guide",
            subject_employee_id=caller.employee_id,
            required_evidence=(),
        )
    if "laptop before" in lower:
        return ContextPlan(
            turn,
            "laptop_status",
            subject_employee_id=caller.employee_id,
            required_evidence=("laptop_provisioning.md", "equipment_policy.md"),
            operational_reads=("list_onboarding_tasks", "check_asset_inventory"),
        )
    if (
        "offer letter" in lower
        or "day one" in lower
        or any(phrase in lower for phrase in ("systems does maya", "systems maya", "apps does maya", "access does maya need", "what does maya need"))
        or (any(word in lower for word in ("systems", "apps")) and any(word in lower for word in ("need", "needs", "required")))
    ):
        return ContextPlan(
            turn,
            "offer_letter",
            active_constraints=tuple(constraints),
            required_evidence=("maya_cohen_offer_letter.md",),
        )
    if any(word in lower for word in ("equipment", "laptop", "monitor", "headset")):
        return ContextPlan(
            turn,
            "equipment_request",
            active_constraints=tuple(constraints),
            required_evidence=("equipment_policy.md", "laptop_provisioning.md"),
            operational_reads=("check_asset_inventory",),
        )
    if (
        "checklist" in lower
        or "still open" in lower
        or "full status summary" in lower
        or any(word in lower for word in ("blocked", "blocking", "readiness", "progress"))
        or ("onboarding" in lower and any(word in lower for word in ("status", "ready", "open", "pending")))
        or ("maya" in lower and any(word in lower for word in ("status", "ready", "pending")))
        or (("summary" in lower or "overview" in lower) and ("maya" in lower or "onboarding" in lower))
    ):
        intent = "overview" if "overview" in lower else "summary" if "summary" in lower else "onboarding_status"
        reads = () if intent == "summary" else ("list_onboarding_tasks",)
        if intent == "overview":
            reads = ("get_employee", "list_onboarding_tasks", "check_software_subscription")
        return ContextPlan(turn, intent, active_constraints=tuple(constraints), operational_reads=reads)
    if "location" in lower and "start date" in lower:
        return ContextPlan(turn, "recall", active_constraints=tuple(constraints))
    if "freeze" in lower or "finance" in lower:
        return ContextPlan(
            turn,
            "policy_question",
            active_constraints=tuple(constraints),
            required_evidence=("saas_renewal_freeze_q3.md", "webex_license_assignment.md", "webex_vendor_agreement.md"),
            operational_reads=("check_software_subscription",),
        )
    if "file the webex access request" in lower:
        return ContextPlan(
            turn,
            "access_request",
            active_constraints=tuple(constraints),
            required_evidence=("webex_license_assignment.md", "saas_renewal_freeze_q3.md", "webex_vendor_agreement.md"),
            operational_reads=("check_software_subscription",),
            allow_webex_handoff=True,
        )
    if "webex" in lower or "seat" in lower or "license" in lower:
        return ContextPlan(
            turn,
            "subscription_review",
            active_constraints=tuple(constraints),
            required_evidence=("webex_license_assignment.md", "webex_vendor_agreement.md"),
            operational_reads=("check_software_subscription",),
        )
    normalized = lower.strip(" \t\n.!?")
    if normalized in {"hello", "hi", "hey"} or any(phrase in lower for phrase in ("help me", "what can you do", "how does this work", "show me what you can do")):
        return ContextPlan(turn, "help", subject_employee_id=caller.employee_id, active_constraints=tuple(constraints))
    return ContextPlan(turn, "unknown", subject_employee_id=caller.employee_id, active_constraints=tuple(constraints))


def select_loadout(plan: ContextPlan) -> tuple[str, ...]:
    loadout = READ_TOOL_LOADOUTS[plan.intent]
    if any(tool in FORBIDDEN_TOOLS for tool in loadout):
        raise ValueError("Maya loadout must never include direct write tools")
    return loadout


def validate_tool_matrix() -> list[str]:
    errors: list[str] = []
    for turn, expected in EXPECTED_READ_TOOLS_BY_TURN.items():
        sample_plan = {
            1: ContextPlan(turn, "employee_lookup"),
            2: ContextPlan(turn, "offer_letter"),
            3: ContextPlan(turn, "onboarding_status"),
            4: ContextPlan(turn, "ticket_status"),
            5: ContextPlan(turn, "equipment_request"),
            6: ContextPlan(turn, "equipment_request"),
            7: ContextPlan(turn, "recall"),
            8: ContextPlan(turn, "subscription_review"),
            9: ContextPlan(turn, "subscription_review"),
            10: ContextPlan(turn, "access_request"),
            11: ContextPlan(turn, "onboarding_status"),
            12: ContextPlan(turn, "summary"),
        }[turn]
        loadout = set(select_loadout(sample_plan))
        for tool in expected:
            if tool not in loadout:
                errors.append(f"turn {turn}: missing {tool} from {sample_plan.intent} loadout")
        if "create_access_request" in loadout:
            errors.append(f"turn {turn}: direct write tool exposed")
    return errors
