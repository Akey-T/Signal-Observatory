# CODEX_PLAN.md — Signal Observatory Next-Phase Execution Plan

**Status:** Active planning contract

**Plan version:** 1.1 — reviewed 2026-09-24

**Owner intent date:** 2026-09-24

**Repository baseline at review:** `main` / `9f77a4d3d23860e5edb9f23820465f249f424267`

This file exists so Codex can execute an owner-approved roadmap without spending substantial context on re-planning the programme. It is an execution-control document, not an acceptance report.

---

## 0. Authority and token-efficient reading protocol

### Always read

For every non-trivial task, read only these first:

1. `AGENTS.md` — non-negotiable engineering rules.
2. `CODEX_PLAN.md` — current owner-approved execution plan.
3. `docs/acceptance/project-phase-acceptance-report.md` — latest factual phase baseline.

Read `README.md` only when current user-facing/product state is relevant to the active task.

### Read task-specific documents only when that task becomes active

**arXiv cursor work**

- `docs/acceptance/e03-arxiv-acceptance.md`
- relevant arXiv source/collector code and tests

**Scheduler qualification**

- `docs/acceptance/e04.6-operational-hardening-acceptance.md`
- `docs/operations/e03-seven-day-scheduler-soak.md`
- `docs/operations/scheduler-punctuality.md`

**Backup / restore**

- `docs/acceptance/e04.5b-backup-restore-acceptance.md`
- `docs/operations/backup-restore.md`

**Attention / GDELT / World Pulse**

- `docs/acceptance/e05-attention-domain-foundation-acceptance.md`
- `docs/acceptance/e06-gdelt-global-news-acceptance.md`
- relevant architecture/source docs

Do **not** re-read every large historical document for every subtask unless an inconsistency requires it. Do not independently re-plan the whole roadmap when the active task is already bounded here.

If current persisted runtime evidence conflicts with a historical acceptance report, preserve the historical report and treat current persisted evidence as current operational truth.

---

# 1. Product direction

Signal Observatory has two product tracks.

## Technology Observatory

- Research — arXiv
- Developer — GitHub
- Community — future/optional community sources

## World Pulse

- Media Attention — GDELT
- Search Attention — planned search-attention source
- Reference / Knowledge Attention — planned Wikimedia source
- Discovery — future non-canonical candidate-story layer required to surface important world events outside the existing curated Topic registry

The long-term product goal is to answer both:

1. **What is happening in technology?**
2. **What is the wider world paying attention to?**

A later `Tech × World` surface may show technology moving from specialist attention into mainstream attention.

### Important product distinction

Monitoring existing curated Topics is **not sufficient** to deliver an “international hot-search / world-important-events” product. World Pulse therefore needs a later discovery layer that can surface source-native candidate stories without silently creating canonical Topics, Events, or Entities.

### Prohibited unless separately authorised

- Trend Score
- Public Attention Score
- Public Concern Score
- Event Importance Score
- silent automatic canonical Topic creation
- silent automatic canonical Event creation
- silent automatic canonical Entity creation
- LLM output modifying Raw or curated Registry state
- a unified cross-source “world hotness” score without an independently approved definition

Collection and deterministic normalization should use **zero LLM tokens by default**. Any future daily AI briefing is a separate optional presentation layer and is not required for source ingestion or ranking.

---

# 2. Current baseline

At this plan revision:

- E00–E05 are implemented and accepted at the development-baseline level.
- E04.6 implementation is complete; historical operational qualification remains failed/incomplete.
- E05 Attention Domain is accepted.
- Alembic head is `20260913_0009`.
- E06 GDELT implementation has **not started**.
- GDELT must not be described as configured, live, healthy, or accepted.
- Historical `scheduler-punctuality-v1` is permanently failed and must not be rewritten.
- The latest phase report records four historical arXiv `incremental child has no partition root` anomalies.
- Current DR evidence is stale relative to `0009`; the latest verified recovery point in the phase report is still a historical `0007` backup.

**Do not reimplement E00–E05.**

The first task must refresh current runtime evidence because the phase report's live evidence cutoff is older than this plan.

---

# 3. Dependency graph — authoritative execution order

Do **not** interpret the P-number sequence as one fully serial queue.

```text
P0-A Current-state refresh
        |
        v
P0-B arXiv historical cursor reconciliation
        |
        +----------------+----------------+----------------+
        |                |                |                |
        v                v                v                v
P0-C Scheduler       P1-A/P1-B DR     P1-C GitHub      P2-A GDELT
qualification        refresh           diagnosis        capability probe
(real time)          + off-host        (read-only)      (non-production)
        |                |                                 |
        |                |                                 v
        |                |                              Probe GO
        |                |                                 |
        +----------------+----------------+----------------+
                                         |
                                         v
                              P2-B GDELT implementation
                                         |
                       scheduler gate + DR gate + owner gate
                                         |
                                         v
                           Production scheduling / LIVE
```

### Hard gating rules

- `P0-A` must occur before any new change.
- `P0-B` must pass before the GDELT capability probe or production GDELT work.
- After `P0-B`, Scheduler qualification, current DR refresh, GitHub diagnosis, and the bounded GDELT probe may proceed in parallel.
- GDELT **implementation** may begin after `P0-B` passes and `P2-A` returns GO, subject to a bounded implementation plan.
- GDELT **production scheduler activation and any LIVE claim** require:
  - the applicable Scheduler qualification gate to pass;
  - the current DR gate to pass; and
  - explicit owner authority.

This distinction intentionally avoids waiting seven days before harmless implementation work while still blocking unsafe production activation.

---

# P0-A — Refresh Current Runtime Evidence

## Objective

Capture current facts before changing code. New 2026-09-23/24 runtime evidence may supersede the live-state numbers in the phase report without rewriting historical acceptance.

## Read-only commands

Run from repository root:

```bash
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git log -1 --oneline --decorate
git diff --check

alembic current
alembic heads
alembic check

docker compose config --quiet
docker compose ps

signal-observatory ops check --json
signal-observatory ops verify-raw --sample 100 --json

signal-observatory arxiv status --json
signal-observatory arxiv cursor-audit --json
signal-observatory arxiv verify-cursors --json

signal-observatory github status --json
signal-observatory github verify-cross-day --json

signal-observatory scheduler status --json
signal-observatory scheduler verify-punctuality --json

signal-observatory backup list --json
```

If a newer read-only verifier exists in the repository, use it only after confirming its semantics from source/help text.

## Deliverable

Record, without modifying runtime state:

- branch / HEAD / origin alignment / dirty paths
- Alembic current/head/drift
- Docker service state
- Raw integrity result
- current arXiv cursor anomaly counts and identities
- current Scheduler continuity and punctuality facts
- latest backup identity and migration head
- current GitHub partial outcome / snapshot facts

## Acceptance

A complete evidence snapshot exists and no command in this phase modified DB, Raw, Registry, scheduler history, or collector state.

## Stop conditions

Stop before implementation if:

- Alembic has multiple heads;
- current DB revision and code head are inconsistent;
- Raw integrity fails;
- cursor facts materially differ from the accepted premise and require re-scoping;
- tracked secrets/runtime Raw/backups appear;
- runtime evidence contradicts a prerequisite in this plan.

---

# P0-B — Historical arXiv Cursor-Lineage Reconciliation

## Problem

Current collector code already creates incremental partition children with explicit root metadata. The phase report records four historical `incremental_part` children that predate the current lineage contract and fail the current verifier.

Treat this first as a **historical compatibility / lineage reconciliation** problem, not as a redesign of incremental partitioning.

## Task 1 — read-only forensic proof

For every currently anomalous child, identify:

- cursor id
- mapping id / Topic
- cursor key
- child window
- root bounds encoded in the key, if present
- checkpoint metadata
- durable ingestion run
- matching Raw request-window metadata
- sibling child cursors
- relevant parent cursor state/history
- whether exactly one root is deterministically provable

## Preferred remediation

### Option A — verifier compatibility — preferred

Teach the read-only verifier to accept an old lineage format **only when** the root is uniquely proven by immutable/persisted evidence such as:

- source mapping identity;
- cursor-key root and child bounds;
- exact window bounds;
- matching Raw request metadata;
- durable ingestion-run lineage.

Do not accept a historical child merely because its key looks plausible.

### Option B — versioned historical metadata remediation

Use only if verifier compatibility is insufficient and root identity is still uniquely provable.

Any metadata remediation must not:

- alter Raw;
- alter Paper observations;
- alter historical query dates;
- change terminal status;
- advance `next_start`;
- change `last_successful_run_at`;
- fabricate an ingestion run;
- convert failed/partial evidence to success.

## Expected file scope

Prefer:

- `collectors/arxiv/src/arxiv_collector/audit.py`
- dedicated historical-lineage fixtures/tests
- `tests/integration/test_arxiv_incremental.py` or a narrowly scoped audit test file

Do **not** modify `service.py` unless a regression test proves a current live-collector defect.

Do not change parser semantics, Paper normalization, Topic matching, Registry mappings, or Raw.

## Required tests

Prove at minimum:

1. current-format partition lineage passes;
2. valid historical-format lineage passes only when uniquely proved;
3. zero-root child fails;
4. ambiguous-root child fails;
5. cross-mapping root mismatch fails;
6. child outside root bounds fails;
7. Raw/window mismatch fails;
8. durable-run absence fails;
9. malformed current parent partition metadata fails;
10. verifier remains read-only.

Also run the applicable repository quality gates.

## Acceptance

```text
cursor_without_durable_run = 0
cursor_without_raw_evidence = 0
cursor_advanced_past_failure = 0
unexplained_cursor_state = 0
modified_records = 0
```

Raw identities/checksums remain unchanged.

## Stop conditions

Stop and report rather than guessing if any child has:

- zero provable roots;
- more than one provable root;
- inconsistent key/window/Raw evidence;
- a reconciliation that would require invented date/run/success evidence.

---

# P0-C — Scheduler Qualification v2

## Principle

E04.6 scheduler hardening is already implemented. Do not redesign the scheduler merely because historical punctuality failed.

The historical `scheduler-punctuality-v1` result is immutable.

The remaining risk is operational host availability, including:

- Windows sleep/hibernation;
- Docker Desktop / Docker engine availability;
- Worker availability/restart behavior;
- host reboot;
- network recovery.

## Task 1 — inspect host/runtime readiness

Inspection is allowed. Do not change Windows power policy, startup configuration, Docker settings, or other OS-level settings without explicit owner approval.

Record:

- Docker Desktop startup behavior;
- Compose/Worker restart configuration;
- sleep/hibernation state relevant to due windows;
- reboot/recovery behavior;
- whether Worker is expected to be running at the qualifying due time.

If a system-setting change is required, present the exact proposed change, risk, and reversal and stop for owner approval.

## Task 2 — new versioned qualification contract

First inspect the current qualification implementation. If `v1` is hard-coded and a new contract requires a code change, make the smallest versioned change with focused tests; never mutate historical v1 rows/results.

Use the currently accepted qualifying job/semantics from E04.6 (currently `arxiv_daily` unless current repository evidence says otherwise).

### Punctuality

Three consecutive real qualifying scheduled windows:

```text
dispatch_delay_seconds <= 300
```

### Continuity

Seven consecutive real natural daily windows:

```text
missing = 0
duplicates = 0
missed = 0
interrupted = 0
```

Manual collection cannot satisfy or repair either gate.

Collector outcome remains independent:

- on-time + partial = on-time but partial;
- late + succeeded = late;
- punctuality never implies complete source data.

## Tests

At minimum, cover:

- version isolation from v1;
- exactly-on-threshold and over-threshold dispatch;
- missed/interrupted/duplicate/missing failures;
- manual-run exclusion;
- collector outcome independence;
- read-only verifier behavior.

## Acceptance

The new contract has enough real elapsed windows and reports both:

- punctuality = PASS;
- continuity = PASS.

Historical v1 remains unchanged.

## Stop condition

Any late, missed, interrupted, duplicate, or missing qualifying window fails that sequence. Start a genuinely new sequence; do not backfill or relabel.

---

# P1-A — Current `0009` Recovery Unit

## Objective

Create a new recovery point for current schema/data, including E05 Attention Domain state.

## Preconditions

- P0-A current-state snapshot completed.
- If P0-B modifies code only, use the accepted post-remediation code baseline when creating the recovery unit.
- Do not wait for seven-day Scheduler qualification to create a current recovery point.

## Create

```bash
signal-observatory backup create --label "post-E05-0009 recovery point" --json
```

## Verify

```bash
signal-observatory backup verify <backup-id> --full --json
signal-observatory backup show <backup-id> --json
```

## Required evidence

- PostgreSQL custom-format dump;
- migration head `20260913_0009` or the then-current explicitly approved head;
- immutable Raw;
- Registry snapshot;
- provenance;
- exact table counts;
- Attention tables including:
  - `attention_documents`
  - `attention_observations`
  - `attention_observation_evidence`

If the approved head changes before backup creation, do not falsely require literal `0009`; record the new approved head and explain why the plan baseline moved.

## Stop conditions

Fail closed if:

- any persisted source lacks a recovery adapter;
- Raw is missing or corrupt;
- migration head differs unexpectedly;
- table counts cannot be verified;
- full backup verification does not pass.

Never edit Raw or a dump to force a pass.

---

# P1-B — Isolated Restore Drill + Off-host Copy

## Restore drill

```bash
signal-observatory backup drill <backup-id> --json
```

Verify:

- isolated PostgreSQL target;
- isolated empty Raw target;
- exact table counts;
- migration head;
- Registry identity;
- Raw checksums;
- source lineage;
- Attention tables;
- read-only API smoke;
- cleanup.

Never restore over active DB or active Raw.

## Off-host copy

A valid DR copy must be on a different physical disk or host.

Codex must **not invent a cloud account, network target, or destination path**. If the owner has not supplied an eligible destination, stop at an owner gate and report exactly what destination properties are required.

If an eligible destination is supplied:

- copy the complete published recovery unit without modification;
- preserve bytes exactly;
- verify destination bytes/manifests using supported tooling or deterministic checksums;
- record destination verification evidence without secrets.

## DR acceptance gate

```text
current verified backup = PASS
isolated restore drill   = PASS
verified off-host copy   = PASS
```

Production GDELT scheduling and LIVE status remain blocked until this gate passes.

---

# P1-C — Diagnose GitHub Partial Outcomes

## Objective

Explain current GitHub partial outcomes. Historical missing snapshot dates remain historical gaps; they are **not** a repair backlog.

## Read-only diagnosis first

Classify persisted partial causes such as:

- request-budget limit;
- primary/secondary rate limit;
- 404 / repository unavailable;
- transport failure;
- runtime limit;
- scheduler interruption;
- tracking-set size;
- other persisted error.

Produce counts and representative evidence by cause.

## Decision gate

Only propose a collector/configuration change if evidence shows a current bounded defect or capacity mismatch. Keep that remediation separate from the diagnosis.

## Prohibited

Do not:

- fabricate missing dates;
- create manual historical snapshots;
- interpolate stars/forks;
- shift first-observation dates;
- relabel manual runs as scheduler evidence.

---

# P2-A — E06 GDELT Capability Probe

## Entry gate

Start only after P0-B cursor-lineage reconciliation passes.

Scheduler qualification and current DR may still be running because this probe is non-production and isolated.

## Objective

Determine whether the official GDELT DOC API can support **daily World Pulse Media Attention** safely and reproducibly.

## Product cadence assumption

World Pulse v1 Media collection:

```text
cadence: once per day
product cutoff: 20:00 America/New_York
persisted timestamps: UTC
```

Use an IANA timezone implementation and respect US daylight-saving transitions. Do not encode one permanent UTC hour for a New York local-time contract.

This decision applies to World Pulse Media v1. Do not reschedule existing arXiv/GitHub jobs as part of E06 unless separately authorised.

## Probe scope

Use only a small number of official requests and bounded windows.

Validate:

- authoritative endpoint/mode;
- query encoding and limits;
- exact time-window semantics;
- response schema;
- zero-result behavior;
- language/translation behavior;
- duplicate/canonical URL behavior;
- result caps/pagination;
- rate/error behavior;
- deterministic source-document identity;
- bounded-history availability;
- suitability for idempotent daily collection.

## Measurement/evidence boundary

```text
Timeline / source count measurement = Attention Observation candidate
ArticleList                         = Evidence sample
```

Never use ArticleList length as a substitute for an independently defined media-attention measurement.

## Probe artifacts

Produce a bounded, reviewable package containing:

- probe methodology;
- exact requests excluding secrets;
- small real fixtures;
- schema findings;
- identity/dedup findings;
- rate/error findings;
- observed limitations;
- GO / NO-GO conclusion;
- proposed production implementation scope if GO.

## Prohibited

Do not:

- write production GDELT Raw;
- add production scheduler jobs;
- add UI LIVE state;
- claim GDELT is live;
- auto-create canonical Topic/Event/Entity;
- crawl article bodies;
- bypass paywalls, authentication controls, anti-bot controls, or rate limits;
- introduce Trend/Public Concern scoring.

## Stop conditions

Return NO-GO or owner review if:

- source behavior cannot support reproducible windows;
- request limits make the intended daily use unsafe;
- source identity cannot be made deterministic enough for idempotence;
- measurement semantics cannot be separated from evidence-list sampling.

---

# P2-B — E06 GDELT Media Attention Collector

## Implementation entry gate

Implementation may begin after:

- P0-B cursor gate passes;
- P2-A returns GO;
- owner approves the bounded implementation plan.

**Do not wait solely for the seven-day Scheduler gate to write/test non-production code.**

## Production activation gate

Production scheduling and any LIVE/healthy claim additionally require:

- applicable Scheduler qualification = PASS;
- current DR gate = PASS;
- explicit owner activation authority.

## Reuse E05

Reuse:

- `AttentionDocument`
- `AttentionObservation`
- `AttentionObservationEvidence`
- `AttentionChannel.MEDIA`

Do not create a competing generic news/article domain.

## Required collector properties

- official API only;
- explicit Registry mappings for Topic-linked observations;
- Raw-first;
- immutable Raw;
- idempotent persistence;
- UTC measurement windows;
- durable cursor/checkpoint;
- bounded retry/rate-limit behavior;
- explicit zero distinct from missing;
- deterministic Coverage integration;
- Operations integration;
- recovery-adapter registration;
- no silent Event/Entity/Topic creation.

## Daily schedule

For initial production:

- once per day;
- target cutoff `20:00 America/New_York`;
- persisted scheduled/start times remain UTC;
- lateness is visible;
- missed intervals remain missing.

## Required tests / acceptance before LIVE

At minimum:

- request/query determinism;
- Raw-before-parse behavior;
- idempotent rerun;
- document identity/dedup;
- measurement/evidence distinction;
- zero vs missing;
- partial/error persistence;
- cursor safety;
- Coverage derivation;
- recovery adapter / backup integration;
- bounded real pilot;
- human evidence review;
- truthful API/UI configured/live/degraded states;
- full repository quality gates.

---

# P3 — World Pulse Expansion and Discovery

World Pulse must eventually surface important world events **outside** the existing curated technology Topic registry. Do not mistake Topic monitoring for global discovery.

## P3-A — Non-canonical World Pulse Discovery Foundation

### Goal

Design a source-native candidate-story layer for “international hot-search / important world events” without automatically creating canonical Topics, Events, or Entities.

### Constraints

- Candidate != canonical Event.
- Candidate != canonical Topic.
- Candidate may be ephemeral or persisted only under an explicitly approved, rebuildable contract.
- E05 `EventCandidate` is a non-canonical contract; do not silently turn it into canonical Event persistence.
- Source-native ordering/counts may be displayed if their meaning is explicit.
- Do not produce a unified cross-source popularity score in this phase.

### Required design questions

Before implementation decide:

- how source-native global candidates enter the system without `topic_id`;
- whether candidate persistence is needed or can be rebuilt from Documents/Raw;
- candidate identity/dedup across repeated daily batches;
- geography/region/language representation;
- story clustering governance;
- review/promotion path, if any, into canonical objects;
- how Media/Search/Reference evidence attaches to a candidate without mislabeling it as canonical truth.

This design requires separate owner approval before schema changes.

## P3-B — Search Attention

Candidate source: Google Trends or another official / explicitly supportable machine-readable source.

Channel: `SEARCH`.

Before implementation perform a bounded capability/access probe. Do not assume an unofficial scraper is an acceptable production source.

Preserve:

- geography;
- source-native observation time;
- query/topic identity semantics;
- zero vs missing;
- source-native ranking/volume definitions.

## P3-C — Reference / Knowledge Attention

Candidate source: Wikimedia Analytics APIs.

Channel: `REFERENCE`.

Prefer official pageview / most-viewed interfaces. Preserve project/language/geography and source-native units.

---

# P4 — World Pulse UI

Do not perform a major homepage redesign after only one source becomes live.

Prefer to wait until at least two World Pulse channels have accepted real evidence and the discovery semantics are defined.

Target information architecture:

```text
SIGNAL OBSERVATORY

WORLD PULSE
  Global / region / country lenses
  Media
  Search
  Reference
  source-native candidate stories

TECHNOLOGY RADAR
  Research
  Developer
  Community

TECH × WORLD
  Cross-channel evidence

SYSTEM HEALTH
  link to /operations
```

Engineering diagnostics remain concentrated in `/operations`.

The UI may show source-native ordering and explicit evidence, but must not imply a single Observatory-wide world ranking unless a later metric definition is independently approved.

---

# P5 — Tech × World

Later analytical goal:

```text
Research
→ Developer
→ Community
→ Media / Search / Reference
```

Any future cross-source analytical metric must:

- be versioned;
- be reproducible from persisted evidence;
- have explicit units and definitions;
- preserve geography/window semantics where relevant;
- distinguish zero from missing;
- not become a generic Trend/Public Concern score without separate owner approval.

---

# 4. Parallelism summary

## Serial prerequisite

```text
P0-A current-state refresh
→ P0-B cursor reconciliation
```

## Parallel lanes after P0-B

```text
Lane A: Scheduler qualification v2 (real-time elapsed evidence)
Lane B: current recovery unit → full verify → restore/off-host
Lane C: GitHub partial diagnosis
Lane D: bounded GDELT capability probe
```

## GDELT implementation

May begin after `P0-B PASS + P2-A GO + owner implementation approval`.

## GDELT production activation / LIVE

Requires all of:

```text
GDELT implementation acceptance
Scheduler qualification PASS
current DR gate PASS
owner activation authority
```

---

# 5. Required repository quality gates

For implementation changes, obey `AGENTS.md` first. Before declaring a code package complete run:

```text
python -m ruff check .
python -m ruff format --check .
python -m mypy apps packages config db collectors
python -m pytest
npm run lint
npm run format:check
npm run typecheck
npm run test
npm run build
docker compose config --quiet
```

When Docker is available and the package affects runtime behavior, also rebuild/start the stack and verify service health as required by `AGENTS.md`:

```text
docker compose up -d --build
docker compose ps
```

When schema changes:

- test the full migration chain from an empty DB;
- test the supported upgrade path;
- run `alembic check`;
- verify a single Alembic head;
- preserve existing data unless the migration explicitly and safely transforms it.

When a change affects Raw/provenance/recovery:

- run the relevant integrity verifier;
- prove no existing Raw bytes were edited;
- update recovery adapters as required.

---

# 6. Codex operating rule — optimized for low token usage

When the owner says **“continue the plan”**:

1. read the three always-required files only;
2. refresh the minimum current facts needed for the active gate;
3. identify the first eligible incomplete task from the dependency graph;
4. read only that task's specific docs/code/tests;
5. state a concise bounded execution package:
   - objective;
   - files expected to change;
   - tests;
   - risks;
   - rollback/reversal where applicable;
   - stop conditions;
6. execute only that bounded package if authorised;
7. do not independently redesign later Epics;
8. preserve historical failed acceptance evidence;
9. stop at explicit owner gates;
10. report evidence succinctly rather than restating the entire programme.

Codex may update **task status/evidence pointers** in this plan after an accepted package, but must not rewrite product direction, gates, or future scope without owner approval.

If current evidence invalidates a premise, stop and report the conflict. Do not silently reinterpret the roadmap.

---

# Execution checkpoint — 2026-09-24 UTC

This is a task-status pointer only; the product direction and gates above are unchanged.

| Package                          | Current result                                                                                                                              | Evidence                                                    |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| P0-A current-state refresh       | Complete                                                                                                                                    | `docs/operations/current-state-2026-09-24.md`               |
| P0-B arXiv historical lineage    | Passed: four old children reconciled by read-only audit, all five integrity outputs zero                                                    | `docs/operations/arxiv-cursor-reconciliation-2026-09-24.md` |
| P0-C scheduler v2                | AC-only sleep change approved/applied; v2 deployed, `PENDING` 0/3; first eligible real window 2026-09-26 02:00 UTC; continuity still failed | `docs/operations/scheduler-v2-readiness-2026-09-24.md`      |
| P1-A current recovery unit       | Passed: `20260924T023237Z-53aec9`, schema `0009`, full verification                                                                         | `docs/operations/recovery-unit-2026-09-24.md`               |
| P1-B isolated restore / off-host | Restore passed; off-host copy pending eligible owner-supplied destination; overall DR gate pending                                          | `docs/operations/recovery-unit-2026-09-24.md`               |
| P1-C GitHub partial diagnosis    | Complete, read-only; current 100-request capacity mismatch identified                                                                       | `docs/operations/github-partial-diagnosis-2026-09-24.md`    |
| P2-A GDELT probe                 | NO-GO at current access point: official API returned 429 twice; no successful schema fixture                                                | `docs/operations/gdelt-capability-probe-2026-09-24.md`      |
| P2-B implementation / LIVE       | Not started; GO, scheduler, DR, and owner gates remain unsatisfied                                                                          | This plan                                                   |
