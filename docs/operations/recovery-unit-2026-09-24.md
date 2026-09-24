# Current recovery-unit evidence — 2026-09-24 UTC

## P1-A — current `0009` backup: PASS

Published backup `20260924T023237Z-53aec9` (`post-E05-0009 recovery point`) contains a PostgreSQL
18.4 custom-format dump, Registry v2 snapshot, Raw copy and manifests. It was created from the
online database at migration `20260913_0009` and independently full-verified at
`2026-09-24T02:35:22.870324Z`.

| Evidence          | Result                                                                                                   |
| ----------------- | -------------------------------------------------------------------------------------------------------- |
| PostgreSQL dump   | 55,429,891 bytes; SHA-256 `acb2e1f17e3e57f955c04099ffea1efeb76613002638b5cce6722dbeb8ee664c`             |
| Tables            | 31; exact counts in the published manifest                                                               |
| Attention tables  | `attention_documents = 0`, `attention_observations = 0`, `attention_observation_evidence = 0`            |
| Registry          | v2, 101 Topics, checksum `f2deee8290c51b0842a8e123626465aa004f9850e136ead93d95258314152394`              |
| Raw               | 5,366 objects, 46,865,555 bytes; all full-verified; 0 missing, checksum, sidecar, or extra-file failures |
| Full verification | `pass`, no warnings; total recovery-unit size 102,343,785 bytes                                          |

The manifest's `git_commit_if_available` is `9f77a4d3d23860e5edb9f23820465f249f424267`:
the P0-B auditor compatibility code was rebuilt and tested but was still uncommitted when the
backup was created. This field must not be presented as a commit containing the P0-B change.
The data/schema recovery unit itself is `0009` and fully verified.

## P1-B — isolated restore: PASS; off-host copy: PENDING owner destination

Drill `signal_observatory_restore_drill_20260924023543_a1b137` passed. An isolated empty
PostgreSQL database and short temporary Raw directory were used. All 31 table counts, migration
`20260913_0009`, Registry identity, 5,366 Raw checksums, arXiv/GitHub lineage samples, and five
read-only API smoke routes matched. Cleanup completed; the drill did not restore over online data.

The backup is currently under the repository's ignored `data/backups/` runtime tree on the same
physical disk. A different physical disk or host destination has **not** been supplied or
verified. Therefore the complete DR acceptance gate remains **PENDING**, despite backup and drill
passing. No off-host copy or production GDELT activation is claimed.
