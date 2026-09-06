# Webex Langfuse Widget Imports

Drag these `.widget.json` files onto a Langfuse dashboard after running the Rachel
Webex baseline traces.

Recommended order:

1. `webex-turn-pass-rate.widget.json`
2. `webex-judge-safety.widget.json`
3. `webex-deterministic-vs-judge.widget.json`
4. `webex-score-volume.widget.json`
5. `webex-check-breakdown.widget.json`

The useful class story is:

```text
Rachel Webex cases -> deterministic webex_* scores -> managed Webex judges -> dashboard
```

The score names used by these widgets are:

- `webex_turn_pass`
- `webex_turn_score`
- `webex_faithfulness`
- `webex_no_overgrant`
- `webex_tool_selection`
- `webex_forbidden_avoided`
- `webex_fact_recall`
- `webex_decision_status`
- `webex_reuse_existing_ticket`
- `webex_reuse_existing_request`
- `webex_approval_persistence`
- `webex_pending_approvals`
- `webex_no_grant_claim`
