# P0-B arXiv historical cursor-lineage reconciliation — 2026-09-24 UTC

## Scope and result

Read-only auditor compatibility was applied to four historical `incremental_part` cursors that
pre-date explicit `partition_root_*` checkpoint fields. The collector, parser, Paper observations,
Topic matching, Registry, existing Raw, and database rows were not changed. Current-format child
checkpoints remain supported.

The old auditor inferred root existence only from the parent cursor's **current** `partition`
checkpoint. Subsequent incremental windows replaced that checkpoint, so valid old children were
reported as having no root. The replacement requires exact key, mapping, Topic, child/root bounds,
UTC window containment, intact root Raw, a terminal arXiv ingestion run, and the root run's intact
partition-child Raw. It rejects a mere matching older probe. For succeeded children, the child
window must also equal the successful query bounds, and Raw for the durable run must match the
child's exact request window. Multiple distinct root queries for one root scope are rejected.

## Persisted lineage

| Topic                   | Mapping                                | Root UTC window                                                         | Root Raw in partition-origin run                                                                                                                               | Children / terminal runs                                                                                                                                         |
| ----------------------- | -------------------------------------- | ----------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| artificial-intelligence | `7c2e1c1c-c965-4e19-b763-4abc7c0749e0` | `2026-08-09T04:10:39.209377+00:00` → `2026-08-19T03:13:47.438605+00:00` | `85f560d9-90e7-4c14-a215-445f3f2d2909`, SHA-256 `6fca4fb3e095f141915c7f0da80887ec8e6488e5800a1775e18c9fa01b2d03b0`, run `21237850-843c-4607-8158-cc463aee8bcc` | `d765b270-b193-497b-b4a8-6e825f3f88b3` / `21237850-843c-4607-8158-cc463aee8bcc`; `9afc03bf-e10b-4b10-85ac-1fcd71ea1e1d` / `08e5f089-6c15-44e9-b481-0a0c384f6047` |
| machine-learning        | `88573826-56a1-4d80-8a0d-97f2bc30a936` | `2026-08-10T02:00:00.123469+00:00` → `2026-08-19T03:13:47.438605+00:00` | `902eaba5-484a-4f1f-bd34-16ae075d6a98`, SHA-256 `8f471a42048e7e61b16af2bd1f0a89771c2afcb290d6bc65d733336855efde54`, run `21237850-843c-4607-8158-cc463aee8bcc` | `5394a23b-91a2-41c4-89ca-9af9fcc9f360` / `21237850-843c-4607-8158-cc463aee8bcc`; `6d7a216f-8d83-43d1-a41b-ff924dab5e44` / `08e5f089-6c15-44e9-b481-0a0c384f6047` |

Both partition-origin root requests were persisted on `2026-08-25` immediately before child
requests. Earlier standalone probes of the same broad windows also exist, but their runs have no
matching partition-child Raw and therefore cannot establish this lineage. Each pair of children
covers its root window contiguously, with matching cursor key, persisted child bounds, request
metadata, and durable run evidence. The parent checkpoint now describes a newer window; it is
not used as historical proof.

## Verification

- Before change: `unexplained_cursor_state = 4`; other three cursor integrity counts were zero.
- After change: `arxiv cursor-audit --json` and `arxiv verify-cursors --json` both passed with
  `cursor_without_durable_run = 0`, `cursor_without_raw_evidence = 0`,
  `cursor_advanced_past_failure = 0`, `unexplained_cursor_state = 0`, `modified_records = 0`.
- `ops verify-raw --source arxiv --full --json`: 2,389/2,389 records checked; zero failures;
  zero modified records.
- The targeted tests cover current and historical pass, absent root, unrelated prior probe,
  conflicting root, cross-mapping, child outside root, root/child Raw window mismatch, missing
  durable run, malformed parent metadata, partial explicit root, and read-only count preservation.

This resolves P0-B only. It does **not** qualify scheduler punctuality, provide a current
`0009` backup, repair GitHub partial outcomes, or activate GDELT.
