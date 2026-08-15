#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [[ -z "${RELEASE_IMAGE:-}" ]]; then
  echo "Set RELEASE_IMAGE to an immutable image tag or digest." >&2
  exit 2
fi

compose_file=${COMPOSE_FILE:-compose.production.yml}
state_dir=${DEPLOY_STATE_DIR:-.deployment-state}
mkdir -p "${state_dir}"
current_image=$(cat "${state_dir}/current-image" 2>/dev/null || true)
if [[ -z "${current_image}" ]]; then
  current_image=${APP_IMAGE:-sdzjoy-platform:current}
fi

printf '%s\n' "${current_image}" >"${state_dir}/previous-image"
echo "Creating the required pre-migration backup..."
APP_IMAGE="${current_image}" docker compose -f "${compose_file}" --profile backup run --rm backup

docker pull "${RELEASE_IMAGE}"
if ! APP_IMAGE="${RELEASE_IMAGE}" docker compose -f "${compose_file}" run --rm web \
  python manage.py migrate --noinput; then
  echo "Migration failed; keeping the previous application image active." >&2
  APP_IMAGE="${current_image}" docker compose -f "${compose_file}" up -d web worker proxy
  exit 3
fi

APP_IMAGE="${RELEASE_IMAGE}" docker compose -f "${compose_file}" up -d db web worker proxy
port=${SDZJOY_PORT:-8080}
for attempt in $(seq 1 20); do
  if curl --fail --silent --show-error "http://127.0.0.1:${port}/healthz/" >/dev/null; then
    printf '%s\n' "${RELEASE_IMAGE}" >"${state_dir}/current-image"
    printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"${state_dir}/last-success"
    echo "Deployment healthy. Previous image retained: ${current_image}"
    exit 0
  fi
  sleep 3
done

echo "Health check failed; rolling application services back." >&2
APP_IMAGE="${current_image}" docker compose -f "${compose_file}" up -d web worker proxy
exit 4

