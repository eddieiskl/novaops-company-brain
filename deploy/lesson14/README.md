# Lesson 14: final-project gateway serving

This adds a separate gateway-backed path for Maya and Webex. Existing deterministic
Compose and EC2 deployment files remain available. The gateway-backed path has been verified on AWS ECS and EFS, then torn down.

## Verified locally, 2026-09-16

- 108 project tests pass, including validation, terminal HTTP status mapping,
  authenticated approval handling, restart/replay, and gateway failure reporting.
- A real Bedrock policy answer succeeds through LiteLLM while the API has invalid
  AWS credentials, no boto3, no direct provider adapter, and no evidence documents.
- All three containers run as UID 10001 with read-only roots. Only MCP mounts the
  writable named volume containing the SQLite approval/business state.
- Approval survives MCP/API restart. Duplicate approval returns the same access
  request; contradictory decisions return 409. Approved Webex access remains
  blocked when the existing subscription lacks capacity.
- Unapproved model aliases and invalid gateway credentials are rejected.
- MCP/gateway outages produce readiness 503 while liveness remains 200; readiness
  recovers after restart. Health checks do not invoke a model.

`verify_local.py` is the repeatable integration check. Its generated evidence is
under ignored `evidence/`; it never writes credentials to the report.

## Local operation

The ignored, mode-0600 `.runtime/gateway.env` contains provider credentials and
`LITELLM_MASTER_KEY`. `.runtime/agent.env` contains the matching `LITELLM_API_KEY`,
`NOVAOPS_APPROVAL_TOKEN`, and trusted integration identity `NOVAOPS_APPROVER_ID`.
These files are excluded from Docker contexts. Do not copy the deployment AWS
credentials into the API image or commit any of these files.

From the project root:

```sh
docker compose -f deploy/lesson14/compose.yaml up -d --build --wait
../.venv/bin/python deploy/lesson14/verify_local.py
docker compose -f deploy/lesson14/compose.yaml down
```

API docs: http://127.0.0.1:18114/docs. Gateway: localhost:4114.
`down` preserves the isolated named volume; do not remove it if its pending
approval records are still needed.

`snapshot.py` makes a source-only commit in a temporary local Git repository. It
does not stage or publish the shared workspace. `.runtime/release.env` supplies
the immutable image tag. Build from the recorded snapshot source, tag all three
images with that SHA, and use `--env-file deploy/lesson14/.runtime/release.env`
when starting them. Record Docker image IDs alongside the verification report.
This local snapshot is not the reviewed public submission commit.

## Trust and persistence limits

The API accepts a trusted caller envelope; it is a course integration API, not a
public identity provider. The approval endpoint uses its own bearer credential
and a server-configured approver (E018 for the fixture). MCP approval tools must
remain internal. The gateway master key is a local demo credential, not a
database-backed per-user quota system. No quota claim is made here.

Run one MCP writer. SQLite approval/business state is durable; ordinary chat
context remains in API memory and does not survive API replacement. This path
does not add a distributed chat store or a queue. Existing core Langfuse
instrumentation is retained; this packaging smoke has tracing disabled and
does not establish new API trace-export evidence. Existing evaluation traces
remain separate evidence.

## Verified on AWS, 2026-09-16

All 16 cloud integration checks passed on stack `novaops-l14-project-df29b7` in us-east-1.
The tested source snapshot is `53603c4c0ebc5cd16585931a83f112e1b512bb89`. It is a local source commit, not a
published update to the submission's reviewed public commit.

- Two ECS services ran: API+MCP together, and LiteLLM separately. Every workload
  container ran as UID/GID 10001. Service Connect used a Cloud Map HTTP namespace.
- The application IAM role explicitly denied Bedrock invocation. The gateway had
  a one-day, model-scoped grant. Both policies were read back and checked.
- The API had no provider keys or data mount. Registry image configurations
  matched the exact locally tested image IDs; task definitions used digests.
- A real cited policy answer succeeded through LiteLLM and the gateway task role.
- A handoff waiting for approval returned HTTP 202. The live test exposed and
  fixed an earlier incorrect HTTP 200/completed response; a regression test covers it.
- After ECS replaced the application task, the pending approval remained on
  encrypted EFS with TLS and IAM mount authorization. Resuming it returned the
  honest Webex capacity block. Duplicate approval reused the same access request;
  a contradictory decision returned 409.
- API ingress was limited to the test caller's /32. Gateway ingress was limited
  to the app security group; EFS NFS ingress was also limited to that group.
- One-hour stop schedules were installed before launching compute. A short
  schedule using the same stop target actually set app desiredCount to zero.
- Cleanup passed all 20 checks. EFS, Cloud Map, security groups,
  repositories, runtime secret, roles, schedules and logs were removed. The ECS
  cluster and task definitions are inactive. Local containers are removed; local
  images, the source bundle and the isolated local test volume are retained.

Machine evidence lives in `evidence/`: `cloud-verification.json`,
`cloud-role-policies.json`, `cloud-image-verification.json`,
`cloud-guardrails.json`, `cloud-autostop.json`, and `cloud-cleanup.json`.
The human-readable record is `../../docs/lesson14-cloud-evidence.md`.

## Repeating the cloud exercise

The deployment uses the dedicated Lesson14 `.env.deploy` in the extracted lesson
folder. It never uses the original course provider identity as a deployment fallback.
The deployer needs ECR, ECS, IAM, Logs, Secrets Manager, Scheduler, EFS, Cloud Map,
and their dependent EC2 networking actions. In particular, EFS mount-target
lifecycle requires **both** `ec2:CreateNetworkInterface` and
`ec2:DeleteNetworkInterface`; selecting all EFS actions alone does not grant them.
The AWS-managed `AmazonElasticFileSystemFullAccess` includes those dependencies.
Temporary broad permissions can be removed or replaced with a scoped policy after
cleanup. The scripts do not modify the deployer's own policies.

Archive `.runtime/cloud-state.json` only after its cleanup evidence passes before
starting another fresh deployment. The script records every created resource and
refuses to start a second deployment over existing state. From the project root:

```sh
../.venv/bin/python deploy/lesson14/cloud_run.py deploy
../.venv/bin/python deploy/lesson14/verify_cloud.py
../.venv/bin/python deploy/lesson14/verify_autostop.py
../.venv/bin/python deploy/lesson14/cloud_run.py cleanup
../.venv/bin/python deploy/lesson14/verify_cleanup.py
```

Run cleanup even if verification fails. It continues independent cleanup when one
resource is denied and records remaining resources for retry. Check the final
verification rather than assuming a successful delete request means cleanup is done.
`update_cloud_release.py` publishes a new locally verified release and updates
changed workloads. The launcher waits for the gateway before starting the app;
tests wait for ECS steady state before sending workflow requests.

The public test API uses temporary HTTP access restricted to one caller IP. This
is a classroom topology; production would need TLS, real caller authentication,
and a transactional service suitable for concurrent writers. The legacy EC2 and
renewal-worker deployment path is separate and was not exercised by this run.

References: [ECS Service Connect](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/create-service-connect.html),
[ECS EFS configuration](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/specify-efs-config.html),
[EFS managed policy](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonElasticFileSystemFullAccess.html).
