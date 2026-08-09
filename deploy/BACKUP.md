# Database backups — what exists, what does not, and how to restore

*Companion to [AUTODEPLOY.md](AUTODEPLOY.md) and [MIGRATION.md](MIGRATION.md).
Written 2026-08-09 (session 25) against operator item **B13**.*

## The one-paragraph version

`rollback.sh` restores the **image**. It has never been able to restore a
**row**. The `yanki_pgdata` volume is the only copy of every analysis, user,
session, organization, audit event and billing row, and every remaining Phase 7
stage adds a migration that runs against it. So: `deploy/backup.sh` takes a
verified dump, `deploy/restore-check.sh` proves a dump can become a working
database, and `deploy.sh` now takes a snapshot automatically before any schema
change — aborting the deploy if the snapshot fails.

**What is still missing is the part only the operator can supply: an off-box
copy and a schedule.** Everything below the fold says how.

---

## What the tooling does

| Command | What it does | Touches production? |
|---|---|---|
| `make backup` / `deploy/backup.sh` | One verified `pg_dump --format=custom` into `~/yanki-backups`, then prunes to the newest 14 | Reads the live database. Writes nothing to it. |
| `make restore-check` / `deploy/restore-check.sh` | Restores the newest dump into a **throwaway container** and asserts it is real | No. There is no flag that makes it touch production. |
| `deploy/deploy.sh` | Snapshots automatically **when, and only when, a migration is pending** | Same read-only dump, before the schema moves |

### `backup.sh` — verified, not just written

A truncated dump is worse than no dump, because it is a backup you believe in.
So the file is written under a `.partial` name and only renamed into place after
three checks pass:

1. **A size floor** (32 KB default) — catches an empty or near-empty write.
2. **A full read-back** — `pg_restore --file=/dev/null` decompresses every entry
   in the archive and discards the SQL, so a truncated or corrupt file fails.
   1.1s on a 2.7 MB dump.
3. **A free-space floor** (512 MB) before it starts — this VPS is shared with
   four other production tenants and a backup that causes a disk-full incident
   has cost more than it saved.

> **Why not `pg_restore --list`.** That was the first version and it was thrown
> away. A custom-format archive stores its table of contents in the **header**,
> so a dump truncated to its first 100 KB still lists all 207 entries and passes
> the check — measured, not assumed. It catches a corrupt header and nothing
> else. A backup check that passes a half-written file is worse than no check,
> because it is the reason nobody looks again.
>
> Both forms run in a short-lived `postgres:16` container with the backup
> directory mounted **read-only**. Piping the dump in on stdin does not work at
> all (reading a custom archive needs to seek, so a perfect dump fails with
> "did not find magic string in file header"), and the other way to give
> `pg_restore` a path — copying the dump into the running production container —
> means writing a full copy of the database into a production container in order
> to run a safety check.

Failing any of them deletes the partial file and exits non-zero.

Dumps are `0600` in a `0700` directory. A dump is the entire database in one
file — password hashes, email addresses, audit payloads — so the permissions are
not decoration.

Retention is **count-based, not age-based**: the newest 14 survive. An age rule
silently leaves you with nothing if the schedule stops; "no backups" should
require somebody to have deleted them.

### `restore-check.sh` — the check that actually matters

`backup.sh` proves the file is a well-formed archive. That is not the same claim
as "this can become a working database", and the gap between those two is where
every backup horror story lives. This closes it by restoring for real, into a
scratch `postgres:16` container on a scratch port, then asserting:

- `pg_restore --exit-on-error` succeeded (a partial restore is a failure, not a
  warning);
- `alembic_version` holds a revision — a schema with no migration stamp is one
  the application refuses to run against;
- `users`, `organizations`, `analyses` and `audit_events` all exist, with their
  row counts printed. **A dump of an empty database restores perfectly and
  protects nothing**, so zero rows is reported loudly rather than passed
  silently.

**Rehearsed for real on 2026-08-09**, against a live production dump:
`alembic_version = 0018_invitations_audit_integrity`, 6 users, 7 organizations,
57 analyses, 35 audit events, 30 tables. 2.7 MB dump of a 17 MB database.

### The pre-migration snapshot

`deploy.sh` compares `alembic current` with `alembic heads` before migrating.
Equal means no schema change and no snapshot — most merges to `main` touch no
schema, and dumping on all of them would push the genuine pre-migration
snapshots out of the retention window with copies of a database that never
changed. Anything else, **including a failure to determine the answer**, takes a
snapshot: the expensive answer is the safe one.

If the snapshot fails, the deploy **aborts before the schema moves**, with the
previous release still serving. The escape hatch, for a real emergency, is
`YANKI_SKIP_PRE_MIGRATION_SNAPSHOT=1` — deliberately verbose, so nobody sets it
by accident.

---

## What is still the operator's (B13)

Two things, and the first one is the one that matters.

### 1. An off-box copy

Everything above writes to `~/yanki-backups` **on the same VPS as the database**.
That survives a bad migration, a dropped table, a truncated column and a
mis-run backfill — the failures that actually happen. It does **not** survive
losing the box. Say that plainly rather than implying more protection than
exists.

Making it real needs a destination and credentials, which are a choice, not an
engineering task. Cheapest options, roughly in order of effort:

```bash
# rsync to any host you already have SSH access to
rsync -az --delete ~/yanki-backups/ backups@elsewhere:/srv/yanki-backups/

# or an S3-compatible bucket (Backblaze B2, Hetzner, Wasabi, R2 …)
rclone sync ~/yanki-backups remote:yanki-backups
```

Whatever you pick, put the credential in `deploy/.env` (gitignored) or in the
copying user's own config — never in the repository, which is public and
gitleaks-gated.

### 2. A schedule

Nothing runs `backup.sh` on a timer today; the pre-migration hook only fires on
a deploy that changes the schema. One line of cron, as the user that owns the
Docker socket:

```cron
# 03:17 UTC daily — off the hour, so it does not collide with everything else
17 3 * * * cd /home/aytek/deploy/yanki-mvp && ./deploy/backup.sh --quiet >> /home/aytek/yanki-backups/cron.log 2>&1
```

Note the path: the **production** checkout is `/home/aytek/deploy/yanki-mvp`,
not the development one. Add the off-box copy to the same line once it exists.

Then verify it, because an unverified schedule is a schedule you find out about
during an incident:

```bash
make restore-check        # after the first scheduled run has fired
```

### 3. Decide the retention window

14 dumps is the default and it interacts with a promise nobody has made yet:
there is no PII retention policy (`pii-retention-and-erasure` in the backlog),
and a backup that outlives an erasure request undoes it. A short window is the
safer default until that policy exists.

---

## Restoring for real

**This is the dangerous one. Read it before you need it.**

There is no script for restoring *into production*, deliberately. It is rare,
irreversible, and every real instance of it has details a script cannot know —
whether to restore the whole database or one table, whether the current data is
partly good, whether the application should be down first.

The shape it takes:

```bash
cd /home/aytek/deploy/yanki-mvp

# 0. FIRST: dump what you have now, however broken. You may need it, and this
#    is the step people skip.
./deploy/backup.sh --label before-restore

# 1. Prove the dump you intend to restore is good, before destroying anything.
./deploy/restore-check.sh ~/yanki-backups/yanki-<stamp>.dump

# 2. Stop the things that write, leaving the database up.
docker compose -p yanki-prod -f deploy/docker-compose.prod.yml stop api worker web

# 3. Restore. --clean --if-exists drops each object before recreating it, so
#    this OVERWRITES the live database. There is no undo but step 0.
docker compose -p yanki-prod -f deploy/docker-compose.prod.yml exec -T db \
  pg_restore -U yanki -d yanki --clean --if-exists --no-owner --exit-on-error \
  < ~/yanki-backups/yanki-<stamp>.dump

# 4. Check the schema stamp matches the image you are about to run. If the dump
#    predates the deployed code's migrations, run `alembic upgrade head` before
#    starting the api — the reverse (code older than schema) is fine.
docker compose -p yanki-prod -f deploy/docker-compose.prod.yml exec -T db \
  psql -U yanki -d yanki -c "select version_num from alembic_version"

# 5. Bring it back.
docker compose -p yanki-prod -f deploy/docker-compose.prod.yml up -d
curl -fsS http://127.0.0.1:8143/healthz
```

Co-tenants (`pulse-prod`, `pulse-realams`, `brier`, `antmedia`, `evrak-app`) are
untouched by all of the above — every command is scoped to the `yanki-prod`
compose project. Keep it that way.
