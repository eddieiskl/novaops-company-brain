# Optional workflow evidence

## Vendor (+5)

`vendor/extractor.py` is a standalone synchronous feature. It makes one forced-tool Bedrock Converse call, normalizes dates and cost, computes missing required fields from the supplied schema metadata, generates one focused follow-up per required gap, and validates with the Draft 2020-12 schema before returning. It has no dependency on the conversational agent.

The three deterministic fixtures produce 0 / 1 / 2 missing required fields. Optional nulls do not create follow-up work, and irrelevant source details are excluded.

## Renewal (+10)

`renewal/workflow.py` is a standalone schedule/event workflow. Its SQLite tables persist the run, internal decision, processed event ids, provider proposal, outbox, applied update, audit identity, and employee notifications. Tests reconstruct the workflow between every stage and replay both inbound events.

Only a complete `approved` provider proposal matching contract `C001`, the expected term, 50-seat limit, USD 22,000 cost, and immediate next-term start can cross the deterministic application gate. Conditional, ambiguous, rejected, mismatched, and wrong-approver paths make no business update. The approved path creates one update and one notification for Rachel after replay; it never grants Webex access.

## Lesson 13 guardrail extension

`evals/run_guardrail_attacks.py` exercises three boundaries: a regular employee attempting to inject a manager-document request, text falsely claiming a write was approved, and an adversarial provider extraction proposal with a mismatched contract. All fail closed.

## Lesson 14 packaging

The API, MCP server, and renewal worker have separate non-root images and health checks. Compose uses dependency-aware startup, a durable volume, and configurable immutable image tags. The local stack was built and exercised through both health endpoints and an MCP-backed agent request. See `docs/deployment.md`.
