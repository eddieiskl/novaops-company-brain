---
prd: "output/novaops-renewal-prd-v1-3-clean/document.md"
sources_checked:
  - "output/novaops-renewal-prd-v1-3-clean/document.md"
  - "novaops-enterprise-agent-dataset/documents/policies/contract_renewal_policy.md"
  - "novaops-enterprise-agent-dataset/documents/internal_memos/saas_renewal_freeze_q3.md"
  - "novaops-enterprise-agent-dataset/documents/internal_memos/contract_owner_cleanup_memo.md"
  - "novaops-enterprise-agent-dataset/database/schema.sql"
  - "novaops-enterprise-agent-dataset/database/seed.sql"
  - "output/prd-review/evidence.queries.md"
---

# PRD review — v1-3-clean

## 1. PRD explained

A daily service reviews SaaS contracts, explains urgency and recommendations, obtains scoped decisions and required clearances, exchanges supplier messages, records future agreements, and activates them at the effective date. It must preserve decisions and avoid duplicate business effects. Models may interpret evidence; they do not acquire decision authority. The acceptance case moves Webex from 40 to 50 seats on July 21, after July 3 confirmation. Stakeholder visions in section 9 are not automatic implementation mandates.

## 2. Gatekeeper findings

### F07 — authority / capability gap

[PRD precondition](<../../Lesson-15 - Course Summary & AI System Design/lesson-15-ai-system-design-sdd/output/novaops-renewal-prd-v1-3-clean/document.md#L151>): “security review must be complete”. No authoritative security reviewer identity or completed clearance record is supplied. The local build must require explicit reviewer configuration; a test assignment is not a Product ruling.

Evidence: [AP002 query](<../../Lesson-15 - Course Summary & AI System Design/lesson-15-ai-system-design-sdd/output/prd-review/evidence.queries.md#L3>) · [schema inventory](<../../Lesson-15 - Course Summary & AI System Design/lesson-15-ai-system-design-sdd/output/prd-review/evidence.queries.md#L75>).

Question: which decision owner and durable record resolve this precondition?

### F08 — authority / capability gap

[PRD precondition](<../../Lesson-15 - Course Summary & AI System Design/lesson-15-ai-system-design-sdd/output/novaops-renewal-prd-v1-3-clean/document.md#L151>): “approval must cover the price ceiling”. The current schema needs commercial approval scope and a separate future agreement record.

Evidence: [AP002 query](<../../Lesson-15 - Course Summary & AI System Design/lesson-15-ai-system-design-sdd/output/prd-review/evidence.queries.md#L3>) · [schema inventory](<../../Lesson-15 - Course Summary & AI System Design/lesson-15-ai-system-design-sdd/output/prd-review/evidence.queries.md#L75>).

Question: which decision owner and durable record resolve this precondition?

### F09 — authority / capability gap

[PRD precondition](<../../Lesson-15 - Course Summary & AI System Design/lesson-15-ai-system-design-sdd/output/novaops-renewal-prd-v1-3-clean/document.md#L151>): “outstanding Finance hold”. Query Q-01 shows AP002 remains needed. Its association is AR001, not a contract renewal. Explicitly resolve this hold; do not infer that a low increment waives it.

Evidence: [AP002 query](<../../Lesson-15 - Course Summary & AI System Design/lesson-15-ai-system-design-sdd/output/prd-review/evidence.queries.md#L3>) · [schema inventory](<../../Lesson-15 - Course Summary & AI System Design/lesson-15-ai-system-design-sdd/output/prd-review/evidence.queries.md#L75>).

Question: which decision owner and durable record resolve this precondition?

## Since the previous review

F01 resolved: v1.3 uses incremental spend. F02 resolved as a requirement: conflicts stay visible; actual case rulings remain required. F03 resolved: uncertain delivery is explicit. F04 resolved: unsupported utilization thresholds removed. F05 resolved: shared RAG no longer prescribed. F06 resolved: contract dates govern attention. F07/F08 remain implementation and authority gaps. F09 identifies the separate AP002 hold.

## 3. Decisions Product needs to make before HLD

Security reviewer ownership and the binding interpretation of AP002 need explicit configuration/decisions. For this authorized local coursework build, AP002 clearance is mandatory and the security owner defaults to unconfigured. E006 is used only in clearly labeled local fixtures. This does not invent a production approval. Source precedence conflicts remain escalated.

## Query evidence

- [Q-01](<../../Lesson-15 - Course Summary & AI System Design/lesson-15-ai-system-design-sdd/output/prd-review/evidence.queries.md#L3>)
- [Q-02](<../../Lesson-15 - Course Summary & AI System Design/lesson-15-ai-system-design-sdd/output/prd-review/evidence.queries.md#L19>)
- [Q-03](<../../Lesson-15 - Course Summary & AI System Design/lesson-15-ai-system-design-sdd/output/prd-review/evidence.queries.md#L38>)
- [Q-04](<../../Lesson-15 - Course Summary & AI System Design/lesson-15-ai-system-design-sdd/output/prd-review/evidence.queries.md#L75>)
