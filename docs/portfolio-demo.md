# Five-minute NovaOps demo

This walkthrough uses the public repository's synthetic fixtures. It demonstrates deterministic application behavior; it does not measure a live model's answer quality.

## 1. Install

```bash
git clone https://github.com/eddieiskl/novaops-company-brain.git
cd novaops-company-brain
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Python 3.11 or newer is required. Dependency installation needs internet access.

## 2. Run the deterministic workflow gate

In a fresh checkout without a `.env` file or exported NovaOps provider settings:

```bash
python evals/run_submission.py --include-optional
```

Expected summary: `produced: 33`, `all_deterministic_checks_pass: true`, and `all_binding_checks_pass: true`. The command writes synthetic results under `.state/`. It does not require AWS or Langfuse credentials in the default local deterministic mode.

The final release produced all 33 records, passed both gates, and passed 145 tests. Lesson 15 also passed four real process-death recovery checks. The exact reviewed source commit is recorded in `SUBMISSION.md`. These are deterministic and local acceptance results, not a fresh live Bedrock or cloud test.

## 3. Open the showcase

```bash
python web/server.py
```

Visit <http://127.0.0.1:4180>. The server binds to localhost.

1. **Story:** explain the operational problem and four workflows.
2. **System:** follow the separation between model proposals and application authority.
3. **Security:** inspect the permission and approval boundaries.
4. **Proof:** connect claims to 145 tests, 33 binding evaluation records, four crash-recovery stages, and recorded deployment evidence. Dashboard counters are release summaries, not continuously refreshed test results.
5. **Live Demo:** inspect Maya's synthetic onboarding view and try a question.

## 4. Explain one engineering decision

Use [the improvement report](../evals/IMPROVEMENT_REPORT.md): a generic green gate missed four defects. Binding checks exposed missing facts, incorrect routing, and unnecessary tool reads. Explain why these checks are more informative than a single aggregate score.

## Scope and limits

- Live Bedrock, remote MCP, and Langfuse modes require separate configuration; see the main README.
- The public cloud evidence record describes the Lesson 14 deployment version; the deployment was cleaned up after verification.
- Synthetic fixtures and deterministic replay do not establish production reliability, identity integration, or performance at scale.
