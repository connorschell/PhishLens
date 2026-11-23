# Database backup and restore

**WBS 5.3** · PhishLens · Connor Schell · CYBR 498W

Automated nightly backups of the production PostgreSQL database, with a restore
that is actually tested rather than assumed.

| File | What it is |
|---|---|
| `backup.sh` | Nightly dump, integrity check, retention pruning |
| `restore_test.sh` | Restores a dump into a scratch database and checks it |
| `phishlens-backup.service` / `.timer` | Nightly at 03:12 UTC |
| `phishlens-restore-test.service` / `.timer` | Mondays at 04:07 UTC |

---

## Install

On the droplet, as `phishlens`:

```bash
cd ~/PhishLens
git pull
chmod +x 05_Deployment/backup/*.sh

sudo mkdir -p /var/backups/phishlens
sudo chown phishlens:phishlens /var/backups/phishlens
sudo chmod 700 /var/backups/phishlens

sudo touch /var/log/phishlens-backup.log
sudo chown phishlens:phishlens /var/log/phishlens-backup.log

sudo cp 05_Deployment/backup/phishlens-*.service /etc/systemd/system/
sudo cp 05_Deployment/backup/phishlens-*.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now phishlens-backup.timer phishlens-restore-test.timer
```

Verify, without waiting for 03:12:

```bash
systemctl list-timers 'phishlens-*'          # both listed with a next-run time
sudo systemctl start phishlens-backup.service
journalctl -u phishlens-backup.service -n 30 --no-pager
ls -lh /var/backups/phishlens/
./05_Deployment/backup/restore_test.sh       # must end with RESTORE TEST PASSED
```

## What the backup does

`pg_dump --format=custom` through `docker compose exec`, because Postgres runs
in a container with no published port outside the Docker network — the same
decision WBS 5.1 made when it left 5432 out of the firewall rules. Custom format
is compressed, restores selectively through `pg_restore`, and refuses a
mismatched target rather than emitting half a database.

Three things in the script exist because of specific failure modes:

- **Write to `.part`, rename on success.** A run killed halfway otherwise leaves
  a truncated file that looks like a backup until the day it is needed.
- **Size floor.** A dump under 20 KB means `pg_dump` succeeded against the wrong
  or an empty database. The schema alone is bigger than that.
- **`pg_restore --list` on every dump.** Reads the archive's table of contents,
  so every stored file has been opened at least once by something that
  understands the format.

Both scripts copy the dump into the container with `docker compose cp` rather
than piping it to `pg_restore` on stdin. The first real run on the droplet
(11/22) failed with `did not find magic string in file header` on a dump whose
first bytes were a correct `PGDMP` header: `docker compose exec -T` gives the
process a non-seekable stdin, which `pg_restore` cannot read a custom-format
archive from. The dump was never the problem, and a verification step that
fails on good backups is worse than none — it teaches you to ignore it.

Retention is 7 daily and 4 weekly (Sunday runs are tagged weekly), so roughly a
month of history in a few megabytes.

## What the restore test does

Restores into a throwaway `phishlens_restore_test` database, which is dropped on
exit — including on failure, via a trap. Production is never written to. It then
checks that all six WBS 3.1 tables came back, that foreign key constraints
survived (a restore without constraints answers every `SELECT` correctly today
and corrupts data on the first write), compares row counts against production,
and runs the `scans × indicators` join the dashboard depends on. Tables existing
is not the same as the application working against them.

`pg_restore --exit-on-error` is deliberate. A restore that logs errors and keeps
going produces a database that is partly right, which is the worst thing to find
out during an actual recovery.

## Restoring for real

If the production database is lost:

```bash
cd ~/PhishLens
docker compose -f docker-compose.yml -f 05_Deployment/docker-compose.prod.yml stop api

set -a; source .env; set +a
docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" db \
  psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE $POSTGRES_DB;"
docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" db \
  psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE $POSTGRES_DB;"

docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" db \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges \
             --exit-on-error /dev/stdin < /var/backups/phishlens/<dump>

docker compose -f docker-compose.yml -f 05_Deployment/docker-compose.prod.yml start api
curl -fsS https://api.usephishlens.app/health
```

Stop the API first. Restoring underneath a running application gives it a
database that changes shape while it is querying it.

## Limitations, stated rather than hidden

**The backups live on the droplet they protect.** If the droplet is lost, so are
they. This is the honest state of WBS 5.3 as scoped: it protects against the
realistic failure for this project — a bad migration, a dropped table, a mistake
during the final-week deployment — not against loss of the host. Mitigating the
host case needs an off-box copy, which is listed below as a known gap rather
than claimed as done.

**No encryption at rest.** The dump contains no message content by design (WBS
3.1 stores a salted fingerprint, never the body — see `00_Admin/data-handling.md`),
but it does contain per-install tokens. Files are `0600` in a `0700` directory
owned by `phishlens`, which is the control that is actually in place.

**Point-in-time recovery is not configured.** Nightly dumps mean up to 24 hours
of loss. WAL archiving would reduce that and is out of scope for a 3-hour task
on a single $12/month droplet.

### Known gaps

- Off-droplet copy (DigitalOcean Spaces, or `scp` to the laptop on a schedule)
- Encryption at rest for the dump files
- An alert when a backup fails — today the failure is only in `journalctl` and
  `/var/log/phishlens-backup.log`
