# Lesson 14 cloud evidence — verified and cleaned up

Recorded 2026-09-16 for the user-authorized Maya/Webex gateway extension.

| Evidence | Result |
| --- | --- |
| Region / stack | us-east-1 / `novaops-l14-project-df29b7` |
| Source snapshot | `53603c4c0ebc5cd16585931a83f112e1b512bb89` (local, not published) |
| Automated project tests | 108 passed |
| Local container checks | 22 passed |
| Live cloud integration checks | 16 passed |
| Automatic stop | Scheduler actually set application desiredCount to zero |
| Cleanup | 20 checks passed; no active exercise compute or EFS remains |
| Public endpoint | Removed with the test deployment |

The deployed path uses two ECS services with distinct IAM task roles. API+MCP has
no model invocation permission; LiteLLM owns the approved model grant. Only MCP
mounts encrypted EFS using TLS and IAM authorization. Cloud Map/Service Connect
provides internal gateway discovery. All workload containers run non-root, and
registry manifests match the exact tested local image configurations.

The live test proved a cited model answer, request validation, HTTP 202 for a
pending handoff, authenticated approval, persistence across application-task
replacement, duplicate approval returning the same request, and a conflicting
decision returning 409. Approval did not manufacture a Webex seat: the resumed
request remained blocked by the subscription capacity limit.

The test caught a completed/pending response bug; `service/api.py` now maps durable
pending handoffs to HTTP 202, covered by `test_real_pending_handoff_is_http_202`.
Deployment setup also now waits for gateway steady state before starting the app.

See [deployment instructions and limits](../deploy/lesson14/README.md). Detailed
machine evidence is retained locally under `deploy/lesson14/evidence/`, including
source bundle, image manifest, cloud verification, IAM policies, ingress rules,
automatic-stop proof and final cleanup verification. Secrets are excluded.

Ordinary chat memory remains process-local; durable approvals/business state is
external. This run uses a trusted caller envelope, one MCP writer, and tracing
disabled; it does not claim production identity, multi-writer SQLite, or new
Langfuse API-export verification. Existing evaluation trace evidence is unchanged.

The [earlier EC2 preparation record](lesson14-ec2-preparation-2026-09-13.md) is
historical design/local-test evidence. That alternative EC2/renewal topology was
not deployed in this ECS gateway exercise. The public submission commit was not
changed or published by this run.
