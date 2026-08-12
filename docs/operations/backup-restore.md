# Backup, Restore, and Disaster Recovery

## Recovery unit

Signal Observatory treats the following as one indivisible recovery unit:

- the PostgreSQL database, including Alembic state and all Bronze/Silver provenance indexes;
- immutable Raw records and their metadata sidecars;
- the curated Registry YAML snapshot used by the database projection;
- checksummed manifests and verification evidence.

A database-only dump is not a valid Observatory backup because it cannot reproduce source
observations without Raw. A Raw-only copy is not valid because it loses Registry identity,
normalization, ingestion runs, and lineage.

## Backup format

Each published directory is named `<UTC timestamp>-<six hex characters>` and contains:

```text
<backup-id>/
  manifest.json
  postgres.dump
  raw/
    arxiv/...
    github/...
  raw-manifest.jsonl.gz
  registry/topics/*.yaml
  verification.json
```

`postgres.dump` is produced by official `pg_dump -Fc`. `raw-manifest.jsonl.gz` records portable
logical paths, byte sizes, compressed-file SHA-256 values, sidecar SHA-256 values, and the
uncompressed source checksum. `manifest.json` is strict and versioned; unknown fields fail
validation. No database URL, password, GitHub token, or other secret is written to these files.

## Create and verify

From the repository root:

```powershell
signal-observatory backup create --label "before E05" --json
signal-observatory backup list --json
signal-observatory backup show <backup-id> --json
signal-observatory backup verify <backup-id> --full --json
```

Creation performs these operations:

1. validates target separation and available disk space;
2. creates a unique directory below `data/backups/.tmp/`;
3. opens a PostgreSQL repeatable-read, read-only snapshot and records exact table counts;
4. runs `pg_dump -Fc` against that exported snapshot;
5. copies immutable Raw records and Registry YAML;
6. writes manifests and verifies the dump catalog, Registry, Raw bytes, sidecars, and checksums;
7. atomically renames the staging directory into the published backup directory.

The PostgreSQL client major version must not be older than the server major version. Local
`pg_dump`/`pg_restore` are preferred. If absent, the running Compose `db` service supplies the
official utilities. A failed run remains under `.tmp/<backup-id>/FAILED.json` and is never listed
as a published backup.

Because the database snapshot is taken first, a collector that completes afterward can leave
newer Raw records in the copy. Verification reports those records as warnings. Missing Raw for a
database response is a failure.

Exit codes for backup commands are `0` pass, `1` warning, `2` invalid/missing evidence, and `3`
configuration, filesystem, database, or PostgreSQL-tool failure.

## Restore

Restore requires explicit targets and never overwrites data:

```powershell
signal-observatory backup restore <backup-id> `
  --database-url postgresql+psycopg://user:password@localhost:5432/empty_restore_db `
  --raw-dir C:\restore\signal-observatory-raw `
  --json
```

Safety gates reject:

- the active Observatory database name;
- a non-PostgreSQL target;
- a target database containing any table;
- a non-empty, symlinked, active, or backup-contained Raw target;
- a backup that fails full preflight verification.

There is deliberately no `--force` option. Raw is copied into a sibling staging directory,
byte-compared with the backup, and atomically published before `pg_restore --exit-on-error`.
After restore, the verifier requires exact domain-table counts, matching Alembic head, matching
Registry version/checksum/topic count, full Raw integrity, arXiv and GitHub lineage samples when
those sources contain matches, and HTTP 200 responses from Registry, Operations, Research,
Development, and Coverage APIs. A restore report is written beside the target Raw directory.

## Recommended isolated drill

```powershell
signal-observatory backup drill <backup-id> --json
```

The drill creates a uniquely named PostgreSQL database and a short Raw work path below the system
temporary directory (avoiding Windows path-length failures), executes the normal restore path,
saves the report under `data/backups/drill-reports/`, then drops the drill database and removes
temporary Raw. Use
`--keep-on-failure` only when forensic inspection is required. It never targets the active
database or active Raw directory.

## Retention and off-host copies

`data/backups/` is ignored by Git. Operators should retain at least one recent verified backup and
one recent passing restore drill report, then copy the complete published backup directory to
storage on a different physical disk or host. Copy only after verification, preserve every byte,
and run `backup verify` against the copied directory. Encryption, access control, remote
replication, and retention automation are deployment responsibilities; this local implementation
does not pretend a same-disk copy is disaster recovery.

## Failure handling

- Do not edit Raw or a dump to make verification pass.
- Investigate `verification.json` or staging `FAILED.json` without exposing secrets.
- If a backup fails, keep the last verified backup as the recovery candidate.
- If a restore drill fails, preserve its report and investigate in isolation.
- Backup or drill outcomes do not count as E03 scheduler success or E04 cross-day evidence.
