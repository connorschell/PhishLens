#!/usr/bin/env bash
#
# PhishLens — restore verification. WBS 5.3.
#
# Restores a dump into a disposable database and checks that what came back is
# a working PhishLens schema. The production database is never touched.
#
#   ./restore_test.sh                       # newest dump in the backup directory
#   ./restore_test.sh /var/backups/phishlens/phishlens_weekly_20261122T030000Z.dump
#
# This exists because an unverified backup is a guess. The deliverable for WBS
# 5.3 is "automated backups with a verified restore test" — the verification is
# the part that makes the claim true, and it is the part most projects skip.

set -Eeuo pipefail

PROJECT_DIR="${PHISHLENS_DIR:-/home/phishlens/PhishLens}"
BACKUP_DIR="${PHISHLENS_BACKUP_DIR:-/var/backups/phishlens}"
SCRATCH_DB="phishlens_restore_test"

fail() { printf 'RESTORE TEST FAILED: %s\n' "$*" >&2; exit 1; }

cd "$PROJECT_DIR"
set -a; source ./.env; set +a
: "${POSTGRES_USER:?}" "${POSTGRES_DB:?}" "${POSTGRES_PASSWORD:?}"

DUMP="${1:-$(find "$BACKUP_DIR" -maxdepth 1 -name 'phishlens_*.dump' | sort -r | head -n1)}"
[[ -n "$DUMP" && -f "$DUMP" ]] || fail "no dump found (looked in $BACKUP_DIR)"

echo "Verifying: $DUMP"
echo "Restoring into scratch database: $SCRATCH_DB"

psql_scratch() {
  docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" db \
    psql --username="$POSTGRES_USER" --dbname="$SCRATCH_DB" -tAq -c "$1"
}

cleanup() {
  docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" db \
    psql --username="$POSTGRES_USER" --dbname=postgres -q \
    -c "DROP DATABASE IF EXISTS $SCRATCH_DB;" >/dev/null 2>&1 || true
  [[ -n "${CTMP:-}" ]] && docker compose exec -T db rm -f "$CTMP" >/dev/null 2>&1 || true
}
trap cleanup EXIT

cleanup
docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" db \
  psql --username="$POSTGRES_USER" --dbname=postgres -q \
  -c "CREATE DATABASE $SCRATCH_DB;" || fail "could not create scratch database"

# The dump is copied into the container rather than piped in on stdin.
# `docker compose exec -T` hands the process a non-seekable stdin, and
# pg_restore reading a custom-format archive that way fails with "did not find
# magic string in file header" on a file that is completely intact. Found on
# the first real run against the droplet, 11/22.
CTMP="/tmp/phishlens_restore_$$.dump"
docker compose cp "$DUMP" "db:$CTMP" > /dev/null \
  || fail "could not copy the dump into the db container"

# --exit-on-error: a restore that logs errors and continues produces a database
# that is partly right, which is the worst outcome to discover during an actual
# recovery. Better to fail here, now, on a scratch copy.
docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" db \
  pg_restore --username="$POSTGRES_USER" --dbname="$SCRATCH_DB" \
             --no-owner --no-privileges --exit-on-error "$CTMP" \
  || fail "pg_restore reported errors"

echo
echo "Structural checks"

# 1. Every table from the WBS 3.1 schema is present.
EXPECTED=(installs model_versions scans indicators url_reputation feedback)
for t in "${EXPECTED[@]}"; do
  got=$(psql_scratch "SELECT to_regclass('public.$t') IS NOT NULL;")
  [[ "$got" == "t" ]] || fail "table '$t' missing from the restored database"
  printf '  table %-16s present\n' "$t"
done

# 2. Foreign keys survived. A dump restored without constraints would still
#    answer every SELECT correctly today and corrupt the data on the first write.
FKS=$(psql_scratch "SELECT count(*) FROM pg_constraint WHERE contype='f';")
(( FKS > 0 )) || fail "no foreign key constraints in the restored database"
echo "  foreign keys     $FKS"

echo
echo "Data checks"

# 3. Row counts, compared against production. Equal counts are expected only if
#    nothing was written between the dump and now, so a larger production count
#    is reported rather than treated as a failure. A *smaller* production count
#    means rows were deleted, which is worth seeing.
for t in "${EXPECTED[@]}"; do
  restored=$(psql_scratch "SELECT count(*) FROM $t;")
  live=$(docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" db \
         psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" -tAq \
         -c "SELECT count(*) FROM $t;")
  flag=""
  (( live < restored )) && flag="   <-- production has FEWER rows than the backup"
  printf '  %-16s restored=%-8s live=%-8s%s\n' "$t" "$restored" "$live" "$flag"
done

# 4. The restored database can actually answer the query the dashboard runs:
#    a join across scans and indicators. Tables existing is not the same as the
#    application working against them.
JOINED=$(psql_scratch "SELECT count(*) FROM scans s LEFT JOIN indicators i ON i.scan_id = s.scan_id;")
[[ "$JOINED" =~ ^[0-9]+$ ]] || fail "the scans x indicators join did not return a count"
echo "  scans x indicators join returned $JOINED rows"

echo
echo "RESTORE TEST PASSED — $DUMP"
echo "Scratch database dropped."
