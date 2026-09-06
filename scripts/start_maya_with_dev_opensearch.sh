#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="${ROOT}/.venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="python3"
fi

OPENSEARCH_HOST="${MAYA_OPENSEARCH_HOST:-127.0.0.1}"
OPENSEARCH_PORT="${MAYA_OPENSEARCH_PORT:-9200}"
MAYA_OPENSEARCH_URL="${MAYA_OPENSEARCH_URL:-http://${OPENSEARCH_HOST}:${OPENSEARCH_PORT}}"
MAYA_RETRIEVER="${MAYA_RETRIEVER:-memory}"

cleanup() {
  if [[ -n "${OPENSEARCH_PID:-}" ]]; then
    kill "${OPENSEARCH_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

cd "${ROOT}"

"${PYTHON}" -B novaops-final-project/dev_opensearch_server.py \
  --host "${OPENSEARCH_HOST}" \
  --port "${OPENSEARCH_PORT}" &
OPENSEARCH_PID="$!"

for _ in {1..40}; do
  if "${PYTHON}" - <<PY >/dev/null 2>&1
from urllib.request import urlopen
urlopen("${MAYA_OPENSEARCH_URL}/_cluster/health", timeout=0.5).read()
PY
  then
    break
  fi
  sleep 0.25
done

echo "Maya dev OpenSearch: ${MAYA_OPENSEARCH_URL}"
echo "Maya dashboard: http://127.0.0.1:4180"
echo "Use the Runtime selector to switch Memory/OpenSearch."

MAYA_OPENSEARCH_URL="${MAYA_OPENSEARCH_URL}" \
MAYA_RETRIEVER="${MAYA_RETRIEVER}" \
"${PYTHON}" -B novaops-final-project/web/server.py
