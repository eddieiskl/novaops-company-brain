# Required evaluation dry run

Date: 2026-09-06

The required evaluation runner loaded the supplied `EVALUATION-INPUTS.yaml`,
reseeded the database between independent inputs and sessions, preserved state
within each session, and produced all 27 required turn records.

## Result

| Gate | Result |
| --- | --- |
| Required records produced | 27 / 27 |
| Generic deterministic checks | pass |
| S2 onboarding replay | pass |
| S9 own-account permission replay | pass |
| S8 heavy-noise write-boundary replay | pass |
| Python test suite | 47 passed |
| Live MCP discovery and policy-answer smoke | pass, 16 tools |
| Bedrock Nova 2 Lite minimal connectivity smoke | pass |
| Official Langfuse trace run | pass, 27 / 27 unique trace ids reachable |
| Required trace metadata | present on 27 / 27 traces |
| `classify → scope → answer` trace topology | present on 27 / 27 traces |

The first local dry run intentionally had no Langfuse trace ids. After explicit
approval of the external destinations, the official run used the live MCP and
Bedrock paths, created 27 unique Langfuse traces, and populated all required trace
cells in `SUBMISSION.md`. `run_submission.py --trace` fails closed when
authentication is missing, and `--update-submission` refuses to edit the trace
table unless all required trace ids are present.

## Commands

```bash
.venv/bin/python -m pytest novaops-final-project/tests -q
.venv/bin/python novaops-final-project/evals/run_maya_s2.py
.venv/bin/python novaops-final-project/evals/run_maya_s9.py
.venv/bin/python novaops-final-project/evals/run_webex_s8.py
.venv/bin/python novaops-final-project/evals/run_submission.py
```
