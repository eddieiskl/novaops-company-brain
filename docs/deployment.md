# Packaging and deployment

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

No AWS access key is baked into an image or passed by Compose. A cloud deployment should use an IAM task/service role for Bedrock and a managed durable database rather than the local Compose SQLite volume. Cloud resources are intentionally not created by repository scripts because provisioning them can incur ongoing cost; the submission records whether an authorized cloud deployment was performed.
