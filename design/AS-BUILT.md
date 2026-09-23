# Lesson 15 — as built

## Baseline and changes

The original runtime contacted the supplier after approval alone, validated against hardcoded commercial terms, and activated the renewal immediately on July 3. It also committed notification work separately from the business update. The new design and implementation require scoped approval, Finance AP002 clearance and an explicitly configured security reviewer; persist a future agreement; and activate on the scheduled effective date in the same transaction as notification intent.

## Capabilities added

- Separate future agreement, scoped authority, clearance, event-payload identity and portfolio-review records.
- Portfolio scan with contract-based notice dates, source-linked recommendations and visible SupportDesk/Figma ownership conflicts.
- Explicit unconfigured security ownership; local fixtures assign E006 only for the demonstration.
- Atomic event handling and effective-date application; process-death replay checks.
- Delivery dispatcher states queued, sending, delivered and uncertain. Recovery never silently retries an uncertain network result.
- Updated evaluation flows for before/after-effective-date assertions and actual trace IDs.

## Decisions and differences

The HLD was written as the implementation baseline during this authorized completion pass; it is not a claim of a separate architecture-board approval. Compared with the supplied reference, this build reuses the existing local SQLite runtime rather than introducing additional deployment components. Recommendations are explainable deterministic review suggestions; the model remains confined to extraction. Supplier and notification adapters stay mocked.

The supplied Lesson 15 archive omits the scoped approval/clearance fixtures mentioned in its homework. Locally authored fixtures under evals/fixtures/lesson15 are explicitly labeled and supplement the older capstone evaluation data. Original course datasets and reference answers are preserved.

## Production limits

The domain API expects trusted internal events; authenticated transport and actor binding remain deployment prerequisites. Security reviewer ownership is a real Product configuration question, not resolved by a test fixture. Real email delivery/reconciliation, availability and latency SLOs, retention policy and multi-worker throughput are not proven by this local build. Other portfolio contracts receive persisted assessments and recommendations; the automated commercial round trip is the supplied Webex reference case.

No live approvals, supplier messages or cloud resources were created. Historical runtime databases were not reset; all acceptance runs used isolated databases. Older completed renewals may reflect the previous early-activation behavior and require an explicit data review before reuse.

## Final validation hardening

Commercial fields now require unique strongly labelled source literals; model proposals cannot fill omissions or select between conflicting values. Explicit approval negation or qualifications prevent automatic agreement acceptance. Nine regression cases demonstrate the former failures and now pass; the full suite passes 145 tests. This bounded parser intentionally routes unsupported wording to human review. It is not a general semantic proof or substitute for authenticated provider ingress.
