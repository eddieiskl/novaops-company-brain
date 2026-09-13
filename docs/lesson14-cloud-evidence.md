# Lesson 14 cloud evidence

This record is filled from machine-checked deployment output; blank values mean cloud provisioning has not yet been authorized or executed.

| Evidence | Value |
| --- | --- |
| Stack | pending authorized deployment |
| Region | `us-east-1` |
| Public API URL | pending authorized deployment |
| Release commit | pending final public release |
| EC2 instance | pending authorized deployment |
| External state | encrypted EFS, pending authorized deployment |
| Verification | local deployment assets pass; live cloud verification pending |

## Local promotion evidence — 2026-09-13

- Full test suite: `92 passed`.
- Optional-inclusive submission evaluation: `33/33`, with deterministic and binding gates passing.
- Cloud Compose render: valid with a 40-character image/release SHA.
- Shell deploy, verify, and cleanup scripts: `bash -n` and ShellCheck clean.
- Rebuilt images: agent `sha256:b5c7c4f4f785a2f8ee422dbfc336da7819370fa90b7accfe5605768910ef4ac3`, MCP `sha256:e11d32d89b81ab56165239b1b55ed3ab5dbc70baa3040742b6c0b6f2afecf331`, renewal `sha256:13a6accf7ae82213f23e97aec54327196d0c20c8c9610d306011545616368bb8`.
- Compose runtime: all three services reached `healthy`; API liveness returned `ok`, readiness returned `ready` with `tool_mode=mcp`, and Docker reported user `novaops` for every application container.
- Cleanup: containers and network removed; the local named state volume was preserved.

## What the deployment proves

- Thin Pydantic request models reject blank, oversized, malformed, and extra input before a workflow runs.
- API, MCP, and renewal event planes use separate container entry points.
- All three application images run as `novaops`, with read-only roots and `no-new-privileges` in cloud Compose.
- Liveness is process-only; readiness checks the MCP dependency without calling a model.
- The exact 40-character release SHA is exposed by `/health/version` and checked by `deploy/aws/verify.sh`.
- Business, approval, outbox, and idempotency state lives on encrypted EFS mounted outside the containers.
- No application container receives AWS model credentials.

## Verification commands

```bash
IMAGE_TAG="$(git rev-parse HEAD)" \
NOVAOPS_RELEASE_SHA="$(git rev-parse HEAD)" \
  docker compose -f docker-compose.cloud.yml config --quiet

python -m pytest -q tests/test_packaging.py tests/test_service_api.py

deploy/aws/verify.sh "http://DEPLOYED_HOST:18080" "$(git rev-parse HEAD)"
```

## Cost and cleanup boundary

The deployer refuses to run without `--approve-costs` and a single-host `/32` ingress CIDR. The current default is budgeted at approximately USD 20/month (about USD 2 for three days) before variable charges. After the instructor no longer needs the endpoint, `deploy/aws/destroy.sh --confirm-delete novaops-company-brain` removes the entire stack and waits for completion.
