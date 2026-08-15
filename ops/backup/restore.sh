#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

for required in RESTORE_BUNDLE RESTORE_DB_HOST RESTORE_DB_NAME RESTORE_DB_USER RESTORE_DB_PASSWORD; do
  if [[ -z "${!required:-}" ]]; then
    echo "Missing required restore setting: ${required}" >&2
    exit 2
  fi
done
if [[ "${RESTORE_DB_NAME}" == "${PRODUCTION_DB_NAME:-sdzjoy}" ]] || [[ "${RESTORE_DB_HOST}" != "restore-db" ]]; then
  echo "Restore drill must target the isolated restore-db service and a non-production database." >&2
  exit 3
fi

stage=$(mktemp -d /tmp/sdzjoy-restore-XXXXXX)
cleanup() { rm -rf -- "${stage}"; }
trap cleanup EXIT

bundle="${RESTORE_BUNDLE}"
if [[ "${bundle}" == *.age ]]; then
  if [[ -z "${AGE_IDENTITY_FILE:-}" ]]; then
    echo "Encrypted backup requires AGE_IDENTITY_FILE." >&2
    exit 4
  fi
  age --decrypt --identity "${AGE_IDENTITY_FILE}" --output "${stage}/bundle.tar.gz" "${bundle}"
  bundle="${stage}/bundle.tar.gz"
fi
tar -C "${stage}" -xzf "${bundle}"
(
  cd "${stage}"
  sha256sum --check SHA256SUMS
)
tar -tzf "${stage}/media.tar.gz" >/dev/null

export PGHOST="${RESTORE_DB_HOST}" PGDATABASE="${RESTORE_DB_NAME}"
export PGUSER="${RESTORE_DB_USER}" PGPASSWORD="${RESTORE_DB_PASSWORD}"
pg_restore --clean --if-exists --no-owner --no-privileges --dbname="${RESTORE_DB_NAME}" \
  "${stage}/database.dump"

migrations=$(psql -Atqc 'SELECT count(*) FROM django_migrations')
users=$(psql -Atqc 'SELECT count(*) FROM accounts_user')
stamp=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p /backups/drills
cat >"/backups/drills/${stamp}.json" <<EOF
{"restored_at":"${stamp}","target":"${RESTORE_DB_NAME}","migration_rows":${migrations},"user_rows":${users},"checksum":"verified"}
EOF
echo "Restore drill completed: migrations=${migrations}, users=${users}"
