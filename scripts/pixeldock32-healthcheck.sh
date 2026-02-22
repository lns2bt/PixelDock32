#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="pixeldock32"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-8}"

if curl --silent --show-error --fail --max-time "${TIMEOUT_SECONDS}" "${HEALTH_URL}" > /dev/null; then
  exit 0
fi

echo "Healthcheck fehlgeschlagen (${HEALTH_URL}) - starte ${SERVICE_NAME} neu" >&2
systemctl restart "${SERVICE_NAME}"
