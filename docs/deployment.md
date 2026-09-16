# Packaging and deployment

The verified Lesson 14 ECS/LiteLLM path is documented in
[`deploy/lesson14/README.md`](../deploy/lesson14/README.md), with
[live evidence and cleanup](lesson14-cloud-evidence.md). The sections below describe
the original deterministic Compose and alternative EC2/renewal deployment.

The project has three physical entry points:

- `agent-api`: validated request plane on container port 8080 (host port 18080 in Compose).
- `mcp`: the tool/data plane on port 9880.
- `renewal-worker`: the schedule/event plane, with no chat endpoint.

All images run as the unprivileged `novaops` user. Liveness does not call a model; readiness checks the configured MCP dependency. Business state is mounted at `/data/novaops.sqlite3` and shared through the `novaops_state` volume for the local demonstration.

Build and start with an immutable Git commit tag:

```bash
IMAGE_TAG="$(git rev-parse HEAD)" docker compose build
IMAGE_TAG="$(git rev-parse HEAD)" docker compose up -d
docker compose ps
curl http://127.0.0.1:18080/health/live
curl http://127.0.0.1:18080/health/ready
```

Stop the demonstration without deleting its durable volume:

```bash
IMAGE_TAG="$(git rev-parse HEAD)" docker compose down
```

No AWS access key is baked into an image or passed by Compose.

## AWS classroom deployment

`deploy/aws/cloudformation.yaml` is the cost-bounded cloud path for the optional Lesson 14 stage. It creates:

- one Amazon Linux 2023 EC2 host, reachable only on API port 18080 from one supplied `/32` address;
- an encrypted EFS file system mounted at `/srv/novaops/state`, outside every application container;
- a keyless Systems Manager instance role; and
- the API, MCP service, and renewal worker as separate read-only, non-root containers.

The cloud Compose file deliberately contains no AWS access-key, secret-key, Bedrock, or Langfuse credential. The classroom deployment runs the deterministic answer path, so application containers do not need model credentials. EFS holds the SQLite state file for business writes, approvals, outbox records, and idempotency keys. This is a small, single-host demonstration topology, not a recommendation to put a high-concurrency production database on NFS; a production evolution would replace it with a managed transactional database.

The instance checks out an exact public Git commit, builds images tagged with that 40-character SHA, starts them with `--no-build`, and reports success only after dependency-aware readiness passes. `/health/version` and `deploy/aws/verify.sh` prove that the reachable service is running the expected release, then exercise one safe agent turn.

Deployment is intentionally double-gated:

1. the release working tree must be clean and its commit must exist on `origin/main`; and
2. the operator must pass `--approve-costs` plus an explicit VPC, subnet, and single-IP CIDR.

Example, after AWS authentication and an explicit cost decision:

```bash
deploy/aws/deploy.sh \
  --approve-costs \
  --vpc-id vpc-EXAMPLE \
  --subnet-id subnet-EXAMPLE \
  --allowed-cidr 203.0.113.8/32
```

At public us-east-1 list prices checked on 2026-09-13, the default `t3.small` is about USD 0.0209/hour, a public IPv4 address is USD 0.005/hour, and 10 GiB gp3 is about USD 0.80/month. With a tiny EFS dataset, budget roughly **USD 20/month** before tax, data transfer, or CPU-credit overage; a three-day review window is roughly **USD 2**. Pricing can change, so re-check the AWS EC2, VPC, EBS, and EFS pricing pages before launch.

Delete every provisioned resource after the review window:

```bash
deploy/aws/destroy.sh --confirm-delete novaops-company-brain
```

The deletion helper waits for the stack to disappear, avoiding a forgotten EC2 instance, public IPv4 address, or EFS file system.
