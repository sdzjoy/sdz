#!/usr/bin/env bash
set -Eeuo pipefail

compose_file=${COMPOSE_FILE:-compose.production.yml}
state_dir=${DEPLOY_STATE_DIR:-.deployment-state}
previous_image=$(cat "${state_dir}/previous-image" 2>/dev/null || true)
current_image=$(cat "${state_dir}/current-image" 2>/dev/null || true)
if [[ -z "${previous_image}" ]]; then
  echo "No retained previous image was recorded." >&2
  exit 2
fi

APP_IMAGE="${previous_image}" docker compose -f "${compose_file}" up -d web worker proxy
port=${SDZJOY_PORT:-8080}
for attempt in $(seq 1 20); do
  if curl --fail --silent "http://127.0.0.1:${port}/readyz/" >/dev/null; then
    printf '%s\n' "${previous_image}" >"${state_dir}/current-image"
    printf '%s\n' "${current_image}" >"${state_dir}/previous-image"
    echo "Application rollback completed. Database and unrelated HVAC services were unchanged."
    exit 0
  fi
  sleep 3
done
echo "Rollback image did not become ready; inspect service logs before any database action." >&2
exit 3

