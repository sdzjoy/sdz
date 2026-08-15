#!/usr/bin/env bash
set -Eeuo pipefail

compose=(docker compose -f compose.production.yml)
cleanup() { "${compose[@]}" --profile backup --profile restore-drill down --volumes --remove-orphans; }
trap cleanup EXIT

"${compose[@]}" up -d db
"${compose[@]}" run --rm web python manage.py migrate --noinput
"${compose[@]}" run --rm web python manage.py shell -c \
  "from accounts.models import User; User.objects.create_user(email='restore-proof@example.invalid', password=None)"
"${compose[@]}" --profile backup run --rm backup
"${compose[@]}" --profile restore-drill up -d restore-db
"${compose[@]}" --profile restore-drill run --rm restore

count=$("${compose[@]}" exec -T restore-db psql -U "${POSTGRES_USER:-sdzjoy}" \
  -d "${RESTORE_POSTGRES_DB:-sdzjoy_restore}" -Atqc \
  "SELECT count(*) FROM accounts_user WHERE email='restore-proof@example.invalid'")
if [[ "${count}" != "1" ]]; then
  echo "Restore sample verification failed: expected 1 user, got ${count}" >&2
  exit 1
fi
echo "Backup and isolated restore sample verified."

