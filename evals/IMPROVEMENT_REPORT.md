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
- Give automated evaluators the prior conversation, declared criteria, and grounding context while keeping large inputs out of propagated metadata.
- Run tests, all 33 deterministic cases, guardrail attacks, Compose validation, and container builds in CI.

## Result

At the end of the Lesson 13 provenance and showcase extension, the implementation passed 87/87 tests. The required submission dry-run produced 27/27 records; the optional-inclusive run produced 33/33. Every record mapped to an explicit expectation, and both runs reported `all_deterministic_checks_pass: true` and `all_binding_checks_pass: true`. This is a historical improvement checkpoint; the current release totals are recorded in the README and submission file.

The polished live read-back found 33 traces, 26 Nova generations, 42 tool observations, 243 deterministic API scores with no non-unit result, and no error observations. All 27 conversational traces include grounding context, all 18 session follow-ups include prior conversation, all six optional traces include their source document or provider reply, and no trace copies large input into propagated metadata. The separate project-level LLM evaluator produced 99 advisory scores with a `0.897` mean; these are intentionally reported separately from the binding promotion gate. Refreshed live trace IDs are recorded in `SUBMISSION.md`.
