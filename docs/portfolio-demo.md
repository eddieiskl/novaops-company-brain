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

On 2026-09-23, the published code at `661c3d77f044d4b4483bc33a3714965a72de67ce` produced all 33 records and passed both gates. This is a deterministic replay result, not a fresh live Bedrock or cloud test.

## 3. Open the showcase

```bash
python web/server.py
```

Visit <http://127.0.0.1:4180>. The server binds to localhost.

1. **Story:** explain the operational problem and four workflows.
2. **System:** follow the separation between model proposals and application authority.
3. **Security:** inspect the permission and approval boundaries.
4. **Proof:** connect claims to recorded evidence. Dashboard counters are release summaries, not continuously refreshed test results.
5. **Live Demo:** inspect Maya's synthetic onboarding view and try a question.

## 4. Explain one engineering decision

Use [the improvement report](../evals/IMPROVEMENT_REPORT.md): a generic green gate missed four defects. Binding checks exposed missing facts, incorrect routing, and unnecessary tool reads. Explain why these checks are more informative than a single aggregate score.

## Scope and limits

- Live Bedrock, remote MCP, and Langfuse modes require separate configuration; see the main README.
- The public cloud evidence record describes the published deployment version. Later local course experiments are not automatically part of this release.
- Synthetic fixtures and deterministic replay do not establish production reliability, identity integration, or performance at scale.
