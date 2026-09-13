#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: deploy/aws/verify.sh BASE_URL EXPECTED_40_CHARACTER_SHA" >&2
  exit 2
fi

BASE_URL="${1%/}"
EXPECTED_SHA="$2"
if [[ ! "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Expected release must be a 40-character lowercase Git SHA." >&2
  exit 2
fi

curl --fail --silent --show-error "$BASE_URL/health/live" >/dev/null
curl --fail --silent --show-error "$BASE_URL/health/ready" >/dev/null
VERSION_JSON="$(curl --fail --silent --show-error "$BASE_URL/health/version")"
python3 -c 'import json,sys; data=json.loads(sys.argv[1]); expected=sys.argv[2]; assert data == {"release_sha": expected}, data' "$VERSION_JSON" "$EXPECTED_SHA"

TURN_JSON="$(curl --fail --silent --show-error \
  -H 'content-type: application/json' \
  -d "{\"thread_id\":\"cloud-smoke-${EXPECTED_SHA:0:12}\",\"caller\":{\"employee_id\":\"E004\",\"user_group\":\"UG_HR\"},\"message\":\"What equipment is available for Maya Cohen?\",\"request_id\":\"cloud-smoke-${EXPECTED_SHA:0:12}\"}" \
  "$BASE_URL/v1/agent/turn")"
python3 -c 'import json,sys; data=json.loads(sys.argv[1]); assert data["status"] in {"completed","blocked"}, data; assert data["workflow_scope"] == "maya_hr", data' "$TURN_JSON"

printf 'Verified liveness, dependency readiness, release SHA, and one safe agent turn.\n'
