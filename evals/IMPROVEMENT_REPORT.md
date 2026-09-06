# Improvement loop

Date: 2026-09-06

## Gate

The required-scope promotion gate is the deterministic 27-turn submission dry-run plus the full pytest suite. The expanded gate runs 33 turns when both optional workflows are included. The dry-run applies the binding fields from `spec/GOLDEN-DATASETS.json`: required and forbidden facts, required and forbidden sources, forbidden tools, and whether a turn needs model-visible tools. Supplemental deterministic checks cover the two required Webex one-shots that have no exact golden entry.

## Baseline

The original runner reported all 27 turns green using only five generic checks. Adding the binding gate exposed four defects:

- M-S-01 turn 5 omitted the authoritative asset identifier/model.
- M-S-01 turn 9 omitted the `7,500` Finance threshold because “seat” won over the Finance intent.
- M-S-01 turn 10 repeated retrieval and subscription reads despite already having the needed state.
- W-I-01 reused `T001` but omitted its recorded `open` status from the answer.

The instrumentation review also found that required evidence names were dropped at the MCP boundary and that the checklist performed two undeclared reads on unrelated policy turns.

## Accepted changes

- Preserve `required_evidence` through both local and remote MCP calls.
- Wrap actual phase, MCP tool, and Bedrock generation execution in Langfuse observations.
- Persist operational reads in thread state and remove implicit checklist reads.
- Prefer explicit Finance/freeze intent over the generic word “seat.”
- Include authoritative asset and ticket-status facts in answers.
- Score every required turn against a readable mapped expectation and attach explanatory score comments.

## Result

The expanded implementation passes 65/65 tests. The required submission dry-run produces 27/27 records; the optional-inclusive run produces 33/33. Every record maps to an explicit expectation, and both runs report `all_deterministic_checks_pass: true` and `all_binding_checks_pass: true`. Refreshed live trace IDs are recorded in `SUBMISSION.md` after the final traced run.
