# E04 GitHub discovery and snapshot Pilot

Pilot status: **Blocked on operator-provided `GITHUB_TOKEN`**

No real GitHub Repository response, candidate, review decision, or Snapshot is claimed in this
report yet. The authenticated Pilot will update this file from persisted Raw/Silver evidence.

## Bounded Pilot scope

The planned six curated Topics use existing Registry mappings and satisfy the required 5–10 Topic
range:

| Topic                  | Explicit Registry query              |     Result cap |
| ---------------------- | ------------------------------------ | -------------: |
| Model Context Protocol | `modelcontextprotocol`; `MCP server` | 10 per mapping |
| PostgreSQL             | `postgres/postgres`                  |             10 |
| Terraform              | `hashicorp/terraform`                |             10 |
| OpenTofu               | `opentofu/opentofu`                  |             10 |
| Prometheus             | `prometheus/prometheus`              |             10 |
| Grafana                | `grafana/grafana`                    |             10 |

The actual query adds the centralized `is:public fork:false` policy. The run is capped at 20
requests and remains serial. Search pagination follows the official `Link` response header.

```powershell
docker compose exec api signal-observatory github discover `
  --topic model-context-protocol --topic postgresql --topic terraform `
  --topic opentofu --topic prometheus --topic grafana `
  --max-results 10 --max-requests 20 --json
```

## Preflight evidence

At `2026-08-11T06:31:08Z`, a no-network dry-run for `model-context-protocol` produced the two
configured queries, reported `auth_configured = false`, made zero requests, and wrote no DB/Raw
state. This proves truthful configuration handling, not Pilot completion.

## Required discovery evidence

| Measure                       | Result                      |
| ----------------------------- | --------------------------- |
| Topics / mappings / queries   | Pending authenticated run   |
| Requests / Raw responses      | Pending authenticated run   |
| Candidates / unique / tracked | Pending authenticated run   |
| New / existing / duplicate    | Pending authenticated run   |
| Fork / archived / disabled    | Pending authenticated run   |
| Search budget and pauses      | Pending authenticated run   |
| Repeat-discovery idempotency  | Pending authenticated rerun |

## Mapping quality review

At least 30 persisted candidate rows will be reviewed manually. Each review will record Topic,
numeric Repository ID, `full_name`, matched query/rank, fork/archive state, relevance outcome, and
notes. Search rank is evidence of query match only; it is not labeled verified relevance until this
review is performed. No Registry mapping will be silently changed from observations.

Result: **0 / 30 reviewed — waiting for authenticated evidence.**

## Snapshot evidence

The first real poll will be the baseline. A second real poll must occur on a later UTC observation
date; a same-day rerun proves idempotency but cannot be represented as a second daily point.

| Measure              | Baseline | Second UTC day |
| -------------------- | -------: | -------------: |
| Repositories due     |  Pending |        Pending |
| 200 / 304 / 404      |  Pending |        Pending |
| Snapshots created    |  Pending |        Pending |
| Changed / unchanged  |  Pending |        Pending |
| Core budget / pauses |  Pending |        Pending |

No date before each Repository's baseline will be added.
