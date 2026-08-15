#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

for required in PGHOST PGDATABASE PGUSER PGPASSWORD; do
  if [[ -z "${!required:-}" ]]; then
    echo "Missing required backup setting: ${required}" >&2
    exit 2
  fi
done

backup_root=/backups
if [[ "${backup_root}" != "/backups" ]]; then
  echo "Unsafe backup root" >&2
  exit 2
fi

stamp=$(date -u +%Y%m%dT%H%M%SZ)
stage=$(mktemp -d "${backup_root}/.stage-${stamp}-XXXXXX")
cleanup() { rm -rf -- "${stage}"; }
trap cleanup EXIT

pg_dump --format=custom --compress=6 --file="${stage}/database.dump"
tar -C /source-media -czf "${stage}/media.tar.gz" .
migration_count=$(psql -Atqc 'SELECT count(*) FROM django_migrations')

cat >"${stage}/manifest.json" <<EOF
{
  "schema": 1,
  "created_at": "${stamp}",
  "database": "${PGDATABASE}",
  "release_image": "${RELEASE_IMAGE:-unknown}",
  "django_migration_rows": ${migration_count},
  "contents": ["database.dump", "media.tar.gz", "SHA256SUMS"]
}
EOF

(
  cd "${stage}"
  sha256sum database.dump media.tar.gz manifest.json > SHA256SUMS
)

bundle="${backup_root}/sdzjoy-${stamp}.tar.gz"
tar -C "${stage}" -czf "${bundle}" database.dump media.tar.gz manifest.json SHA256SUMS

upload_file="${bundle}"
if [[ -n "${AGE_RECIPIENT:-}" ]]; then
  age --recipient "${AGE_RECIPIENT}" --output "${bundle}.age" "${bundle}"
  upload_file="${bundle}.age"
fi
sha256sum "${upload_file}" >"${upload_file}.sha256"

if [[ -n "${OFFSITE_DEST:-}" ]]; then
  if [[ -z "${AGE_RECIPIENT:-}" ]]; then
    echo "Offsite copy requires AGE_RECIPIENT; refusing plaintext upload." >&2
    exit 3
  fi
  rsync --archive --protect-args "${upload_file}" "${upload_file}.sha256" \
    "${OFFSITE_DEST%/}/"
fi

ln -sfn "$(basename "${bundle}")" "${backup_root}/latest.tar.gz"
if [[ -n "${AGE_RECIPIENT:-}" ]]; then
  ln -sfn "$(basename "${bundle}.age")" "${backup_root}/latest.tar.gz.age"
fi

find "${backup_root}" -maxdepth 1 -type f -name 'sdzjoy-*.tar.gz*' \
  -mtime "+${BACKUP_RETENTION_DAYS:-14}" -delete
echo "Backup completed: $(basename "${upload_file}")"
