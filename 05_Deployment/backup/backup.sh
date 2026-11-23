#!/usr/bin/env bash
#
# PhishLens — nightly PostgreSQL backup. WBS 5.3.
#
# Runs on the droplet as the `phishlens` user, driven by phishlens-backup.timer.
# Writes one custom-format dump per run and prunes old ones.
#
#   ./backup.sh            # normal run
#   ./backup.sh --verbose  # echo each step
#
# Custom format (-Fc) rather than plain SQL: it is compressed, it can be
# restored selectively with pg_restore, and it refuses to restore into a
# mismatched server rather than emitting half a database.

set -Eeuo pipefail

PROJECT_DIR="${PHISHLENS_DIR:-/home/phishlens/PhishLens}"
BACKUP_DIR="${PHISHLENS_BACKUP_DIR:-/var/backups/phishlens}"
KEEP_DAILY="${PHISHLENS_KEEP_DAILY:-7}"
KEEP_WEEKLY="${PHISHLENS_KEEP_WEEKLY:-4}"
LOG_FILE="${PHISHLENS_BACKUP_LOG:-/var/log/phishlens-backup.log}"

log() { printf '%s  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE" >&2; }

# Any failure is reported with the line that caused it. A backup job that fails
# quietly is worse than no backup job: it produces the belief that backups exist.
trap 'log "FAILED at line $LINENO (exit $?)"' ERR

[[ "${1:-}" == "--verbose" ]] && set -x

cd "$PROJECT_DIR"

# Credentials come from the server's own .env, which is generated on the droplet
# in WBS 5.2 and never copied from the laptop. Nothing is hardcoded here, and
# the password is passed to the container through the environment rather than
# on a command line, where it would be visible in `ps`.
set -a
# shellcheck disable=SC1091
source ./.env
set +a

: "${POSTGRES_USER:?POSTGRES_USER not set in .env}"
: "${POSTGRES_DB:?POSTGRES_DB not set in .env}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD not set in .env}"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DOW="$(date -u +%u)"          # 7 = Sunday
[[ "$DOW" == "7" ]] && TAG="weekly" || TAG="daily"
OUT="$BACKUP_DIR/phishlens_${TAG}_${STAMP}.dump"

log "starting $TAG backup -> $OUT"

# Written to a .part first and renamed on success, so a run interrupted halfway
# never leaves a truncated file that looks like a usable backup.
docker compose exec -T \
  -e PGPASSWORD="$POSTGRES_PASSWORD" \
  db pg_dump \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --format=custom \
    --compress=9 \
    --no-owner \
    --no-privileges \
  > "${OUT}.part"

mv "${OUT}.part" "$OUT"
chmod 600 "$OUT"

SIZE=$(stat -c %s "$OUT")
log "wrote $OUT ($SIZE bytes)"

# A dump smaller than this is a dump of an empty or broken database. The schema
# alone is larger than 20 KB, so this catches the case where pg_dump succeeded
# against the wrong database and returned almost nothing.
if (( SIZE < 20000 )); then
  log "WARNING: dump is suspiciously small ($SIZE bytes) — check the database"
  exit 2
fi

# Integrity check: pg_restore --list reads the archive's table of contents and
# fails on a corrupt file. Cheap, and it means every stored dump has been opened
# at least once.
if ! docker compose exec -T db pg_restore --list /dev/stdin < "$OUT" > /dev/null 2>&1; then
  log "WARNING: pg_restore could not read the table of contents of $OUT"
  exit 3
fi
log "table of contents verified"

# Retention: keep the newest N of each tag. Sorted by name, which is safe
# because the timestamp is ISO-8601 basic format and therefore sorts by time.
prune() {
  local tag="$1" keep="$2" f
  mapfile -t files < <(find "$BACKUP_DIR" -maxdepth 1 -name "phishlens_${tag}_*.dump" | sort -r)
  for f in "${files[@]:$keep}"; do
    rm -f -- "$f"
    log "pruned $f"
  done
}
prune daily  "$KEEP_DAILY"
prune weekly "$KEEP_WEEKLY"

log "backup complete"
