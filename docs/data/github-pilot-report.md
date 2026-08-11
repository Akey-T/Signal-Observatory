# E04 GitHub discovery and snapshot Pilot

Evidence date: 2026-08-11 UTC

Pilot status: **Authenticated discovery and baseline complete; second UTC-day Snapshot pending**

This report records only persisted evidence from the local acceptance environment. The token is
never printed or stored in this document.

## Bounded Pilot scope

The Pilot used six curated Topics and existing Registry mappings:

| Topic                  | Registry query                       |     Result cap |
| ---------------------- | ------------------------------------ | -------------: |
| Model Context Protocol | `modelcontextprotocol`; `MCP server` | 10 per mapping |
| PostgreSQL             | `postgres/postgres`                  |             10 |
| Terraform              | `hashicorp/terraform`                |             10 |
| OpenTofu               | `opentofu/opentofu`                  |             10 |
| Prometheus             | `prometheus/prometheus`              |             10 |
| Grafana                | `grafana/grafana`                    |             10 |

The client added the centralized `is:public fork:false` policy. Execution was serial and capped at
20 requests. A dry-run first confirmed six Topics, six mappings, seven planned queries, configured
authentication, and zero network or persistence writes.

## Discovery evidence

| Measure                                |                            Initial run |                        Identical rerun |
| -------------------------------------- | -------------------------------------: | -------------------------------------: |
| Ingestion run                          | `166ffe35-816e-49c3-91d3-f269c9c32a89` | `e5a89c9b-bc7c-40a1-a3eb-cf9c58b3ac67` |
| Result                                 |                              Succeeded |                              Succeeded |
| GitHub Search requests / Raw responses |                                  6 / 6 |                                  6 / 6 |
| Candidate rows received                |                                     60 |                                     60 |
| Unique repositories                    |                                     55 |                                     55 |
| New / existing repository observations |                                 55 / 5 |                                 0 / 60 |
| Topic matches added                    |                                     60 |                                      0 |
| Tracked / candidate                    |                                 51 / 4 |                              Unchanged |
| Forks / archived                       |                                  0 / 5 |                              Unchanged |
| Errors / rate pauses                   |                                  0 / 0 |                                  0 / 0 |

Although seven queries were planned, the first Model Context Protocol query filled that mapping's
result cap, so the second mapping query required no network request. The initial run's cross-Topic
duplicate ratio was `0.083333`. After both runs, the Search budget was 18 remaining of 30. The
identical rerun added no Repository or match record, demonstrating real-network idempotency.

## Mapping quality review

Thirty persisted rows were reviewed manually: the five highest-ranked rows for every Pilot Topic.
Search rank is query-match evidence, not verified relevance.

|   # | Topic      | Repository ID | Repository                          | Rank | Review                                |
| --: | ---------- | ------------: | ----------------------------------- | ---: | ------------------------------------- |
|   1 | MCP        |     960665821 | `microsoft/mcp-for-beginners`       |    1 | Direct                                |
|   2 | MCP        |     944976593 | `tadata-org/fastapi_mcp`            |    2 | Direct                                |
|   3 | MCP        |     954963562 | `mrexodia/ida-pro-mcp`              |    3 | Direct                                |
|   4 | MCP        |     956472076 | `mcp-use/mcp-use`                   |    4 | Direct                                |
|   5 | MCP        |     952238700 | `awslabs/mcp`                       |    5 | Direct                                |
|   6 | PostgreSQL |     214587193 | `supabase/supabase`                 |    1 | Ecosystem                             |
|   7 | PostgreSQL |      15111821 | `grafana/grafana`                   |    2 | Broad                                 |
|   8 | PostgreSQL |      20787122 | `PostgREST/postgrest`               |    3 | Ecosystem                             |
|   9 | PostgreSQL |     683347556 | `tursodatabase/turso`               |    4 | Broad                                 |
|  10 | PostgreSQL |     198484780 | `beekeeper-studio/beekeeper-studio` |    5 | Broad                                 |
|  11 | Terraform  |      17728164 | `hashicorp/terraform`               |    1 | Direct                                |
|  12 | Terraform  |     678083094 | `opentofu/manifesto`                |    2 | Ecosystem; archived historical record |
|  13 | Terraform  |      93444615 | `hashicorp/terraform-provider-aws`  |    3 | Ecosystem                             |
|  14 | Terraform  |      58478671 | `shuaibiyy/awesome-tf`              |    4 | Ecosystem                             |
|  15 | Terraform  |     232603801 | `hashicorp/terraform-cdk`           |    5 | Ecosystem; archived                   |
|  16 | OpenTofu   |     678083094 | `opentofu/manifesto`                |    1 | Direct historical candidate; archived |
|  17 | OpenTofu   |     679421146 | `opentofu/opentofu`                 |    2 | Direct                                |
|  18 | OpenTofu   |      23267883 | `semaphoreui/semaphore`             |    3 | Ecosystem                             |
|  19 | OpenTofu   |      59522149 | `gruntwork-io/terragrunt`           |    4 | Ecosystem                             |
|  20 | OpenTofu   |      58478671 | `shuaibiyy/awesome-tf`              |    5 | Ecosystem                             |
|  21 | Prometheus |     212639071 | `bregman-arie/devops-exercises`     |    1 | Broad                                 |
|  22 | Prometheus |      15111821 | `grafana/grafana`                   |    2 | Ecosystem                             |
|  23 | Prometheus |       6838921 | `prometheus/prometheus`             |    3 | Direct                                |
|  24 | Prometheus |     129717717 | `grafana/loki`                      |    4 | Broad / tangential                    |
|  25 | Prometheus |     109162639 | `thanos-io/thanos`                  |    5 | Ecosystem                             |
|  26 | Grafana    |      15111821 | `grafana/grafana`                   |    1 | Direct                                |
|  27 | Grafana    |      54400687 | `grafana/k6`                        |    2 | Broad / adjacent                      |
|  28 | Grafana    |     129717717 | `grafana/loki`                      |    3 | Ecosystem                             |
|  29 | Grafana    |     244694886 | `ccfos/nightingale`                 |    4 | Broad / tangential                    |
|  30 | Grafana    |     325724738 | `grafana/pyroscope`                 |    5 | Ecosystem                             |

Review outcome: **23 of 30 Direct or Ecosystem; 7 of 30 Broad or tangential; 0 forks.**

Slash-like text queries such as `postgres/postgres` are broad GitHub Search evidence rather than an
exact-repository selector. This is surfaced for later curated Registry review. The Pilot did not
silently change any Registry entry or create a Topic.

## Snapshot evidence

| Measure                         |                               Baseline |                         Same-day rerun | Second UTC day |
| ------------------------------- | -------------------------------------: | -------------------------------------: | -------------: |
| Ingestion run                   | `d839564c-0b69-4eec-9759-d7dc3b79e856` | `cfaa8aff-5900-4617-82eb-1b48ff2c6776` |        Pending |
| Repositories due                |                                     51 |                                      0 |        Pending |
| Requests / Raw responses        |                                51 / 51 |                                  0 / 0 |        Pending |
| HTTP 200 / errors / rate pauses |                             51 / 0 / 0 |                              0 / 0 / 0 |        Pending |
| Snapshots created               |                                     51 |                                      0 |        Pending |
| Core budget remaining           |                           4949 of 5000 |                              Unchanged |        Pending |

The baseline created one immutable Snapshot per due tracked Repository. The immediate rerun made no
request and wrote no Snapshot. A second point will be accepted only after a real later UTC date and
the normal due interval; clock manipulation or fabricated backfill is prohibited.

## Raw evidence and lineage

The Pilot persisted 63 immutable Raw HTTP responses: 12 `repository_search` responses and 51
`repository` responses, all HTTP 200.

One verified end-to-end example is Repository ID `960665821`,
`microsoft/mcp-for-beginners`, observed on `2026-08-11`:

- Snapshot source: `full_200`
- Stars: `16958`
- Snapshot run: `d839564c-0b69-4eec-9759-d7dc3b79e856`
- Snapshot Raw checksum prefix: `73aaf6`
- Discovery Raw checksum: `15ff666946...51c142`

The numeric Repository identity connects the discovery match, immutable Search Raw record, current
Repository record, immutable Repository Raw record, Snapshot, and ingestion run.

## API and Web evidence

`/api/sources/github/status` reported healthy authenticated collection with 51 tracked repositories
and 51 snapshots. `/api/topics/model-context-protocol/development` reported 9 tracked repositories,
80,511 stars, 14,015 forks, and 7 repositories pushed in 30 days. Deltas are correctly absent with
only a baseline.

Browser acceptance passed `/`, `/topics`, and `/topics/model-context-protocol`. The Topic page
rendered real GitHub metrics, five Repository links, and match evidence with zero console warnings
or errors.

## Remaining Pilot gate

Run the normal Snapshot collector after repositories become due on a later UTC observation date,
then record changed/unchanged counts and final Core budget here. Until that evidence exists, E04 is
not finally accepted.
