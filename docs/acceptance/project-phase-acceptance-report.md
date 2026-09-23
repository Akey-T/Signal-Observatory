# 核心平台已通过，但调度、Cursor 完整性与灾备仍阻止 E06 上线

**项目：** Signal Observatory

**报告用途：** 提供给 GPT，作为制定下一阶段目标、范围和验收标准的事实基线。

**运行证据截止：** 2026-09-22 08:24 UTC

**发布复核：** 2026-09-24；实现与文档基线 `eb950b0405a9448f5378efd39f7ccf742a063037` 已推送至 `origin/main`。

**阶段结论：** **E00–E05 开发基线阶段性通过；E06 依赖已满足但未实现。当前不得宣称全面运营通过，也不得启用生产 GDELT 调度。**

## Executive Summary

- **代码和部署基线已发布。** 原 52 项工作树改动完成逐项边界审查，并以 `e737300`（实现、迁移、测试）和 `eb950b0`（架构、运营、验收文档）分批推送。审查修复了 arXiv threshold 环境变量未生效，以及 E05 跨 Source lineage/乱序旧数据覆盖两类问题。没有提交 `.env`、Token、运行时 Raw 或 backup。
- **质量与 CI 合格。** 2026-09-24 本地门禁为 Python `199 passed / 2 skipped`、前端 `33 passed`，lint、format、mypy、typecheck 和 build 均通过；Compose 重建后四个服务 healthy，PostgreSQL 为 `20260913_0009 (head)` 且 `alembic check` 无 drift。GitHub CI run [`35933590057`](https://github.com/Akey-T/Signal-Observatory/actions/runs/35933590057) 的 `frontend` 与 `backend` job 均通过。
- **数据继续增长，但健康状态仍为 degraded。** arXiv 已观测约 16.6k 篇论文，GitHub 已知 546 个仓库并形成 32 个 snapshot dates；两源 2026-09-22 均产生新数据，但最新 run 均为 `partial`。
- **最紧急的新问题是 Cursor verifier 失败。** 42 个 arXiv parent cursors 中 41 succeeded、1 failed；没有 cursor 越过失败、缺 Raw 或缺 durable run，但存在 4 个 `incremental child has no partition root` 异常。应先解释并修复 lineage，再扩大数据源。
- **运营可靠性和灾备仍未闭环。** 最近七个 arXiv 日窗口缺少 2026-09-19，E04.6 历史准时性资格固定为 `FAILED 0/3`；最新 verified backup 仍停在 `0007`，落后当前 `0009`，且尚无已验证异盘/异主机副本。

## 1. 建议 GPT 采用的下一阶段目标

### Goal 1 — 修复 arXiv Cursor lineage 异常

**优先级：P0，必须先于 E06 生产实现。**

目标是解释并消除 4 个 `incremental child has no partition root` 异常，同时保持 Raw 不可变、已有 parent cursor 不倒退、不把失败伪装成成功。

建议验收条件：

1. 为四个异常 cursor 建立可复核 root/child lineage 或明确、版本化的历史兼容解释；
2. `cursor_without_durable_run = 0`；
3. `cursor_without_raw_evidence = 0`；
4. `cursor_advanced_past_failure = 0`；
5. `unexplained_cursor_state = 0`；
6. 增加 fresh-chain、历史数据库和异常 fixture 回归测试；
7. 不修改既有 Raw payload，不手工推进 cursor。

### Goal 2 — 已完成：固化并推送 E04.6/E05/0009 基线

**状态：2026-09-24 完成。**

实现、迁移、测试和文档已分批提交并推送；候选路径与 staged index 均完成敏感信息和运行时数据复核，GitHub CI 已通过。未使用 destructive reset，也没有丢弃用户成果。下一阶段不应再次把这项工作列为未完成目标。

### Goal 3 — 建立新的真实 Scheduler 资格窗口

**优先级：P0。**

历史 `scheduler-punctuality-v1` 已终结为 `FAILED 0/3`，不能覆盖或重算。最近七个 arXiv 日窗口仅观察到 6 个，缺少 2026-09-19；2026-09-16 还记录了真实 `worker_unavailable_at_due_time`。虽然 9 月 21 日和 22 日 arXiv 均在计划时间后约 0.03 秒内启动，但尚不足以形成新的资格结论。

建议验收条件：

1. 修复 Docker Desktop 自动启动、主机休眠和 Worker 长期可用性；
2. 用新的版本化 qualification contract，不改写 `v1` 历史；
3. 连续三个真实计划窗口 dispatch delay `≤300s`；
4. 连续七个真实自然日无 missing、duplicate、missed 或 interrupted；
5. 手工补跑不得计入 Scheduler 成功；
6. timing result 与 collector outcome 保持独立。

### Goal 4 — 为当前 0009 基线刷新灾备

**优先级：P1，必须先于生产 GDELT 调度。**

最新 verified backup 是 2026-08-19 的 `20260819T110243Z-97d468`，migration head 为 `20260813_0007`。它证明旧 recovery unit 工具链曾通过，但不能恢复当前 E05 表和 `0009` constraint 修复。

建议验收条件：

1. 新 backup 包含 custom-format PostgreSQL dump、checksummed Raw、Registry 和 provenance；
2. migration head 为 `20260913_0009`；
3. 在隔离、空且非活动目标上完成 restore drill；
4. 精确核对全部表计数、E05 三张 Attention 表、Registry、Raw 和 lineage；
5. 生成一份不同物理磁盘或异地主机上的 verified copy；
6. 不覆盖现有运行数据库或 Raw。

### Goal 5 — 受控启动 E06 GDELT capability probe

**优先级：P2。** 可在 Goal 1–2 完成后开展非生产 probe；生产调度必须等待 Goal 3–4 通过。

第一步只做官方 GDELT DOC API 的小规模、可重复 capability probe，并保存 fixture。不要直接实现全量 collector 或启用调度。

建议首阶段交付：

1. 官方 endpoint、请求限制、返回 schema 和时间窗口语义记录；
2. 一组小型、可复现 fixture；
3. Timeline/raw-count 与 ArticleList evidence 的能力边界；
4. 查询长度、分页、零结果、语言、重复 URL、限流与错误行为记录；
5. 明确的 go/no-go 结论及后续 migration、Raw、parser、Coverage、API/UI 拆分计划。

## 2. Epic 状态矩阵

| Epic                          | 当前状态               | 已证实能力                                                        | 尚未闭环                                                     |
| ----------------------------- | ---------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------ |
| E00–E02 Foundation / Registry | 已实现                 | Raw/Silver、Registry YAML、校验、同步、审计、API/CLI              | 缺少逐 Epic 独立 acceptance 索引                             |
| E02.5 Read-only Experience    | 已实现                 | Registry、Topic、Operations 只读页面                              | 不得展示无观测支持的趋势指标                                 |
| E03 arXiv                     | 功能已验收             | 官方 API、Raw-first、可恢复 incremental、历史 Recovery soak `7/7` | 当前 rolling continuity 失败；Cursor verifier 有 4 个异常    |
| E04 GitHub                    | 功能及跨日证据已验收   | 官方 API、numeric ID、ETag、不可变 daily snapshots                | 最新 run 持续 partial；377 个 expected dates missing         |
| E04.5 Data Health             | 已实现                 | Health、Freshness、Coverage、Raw integrity 分离                   | 当前 overall state 为 degraded                               |
| E04.5B Backup/Restore         | 工具链已验收           | `0007` recovery unit 和隔离 restore drill 通过                    | 当前 `0009` backup、restore drill、off-host copy 未完成      |
| E04.6 Operational Hardening   | 实现通过，运营资格失败 | Scheduler evidence、准时性与 outcome 分离                         | `v1 FAILED 0/3`；当前七日 continuity failed                  |
| E05 Attention Domain          | 已验收                 | source-neutral Document、Observation、Evidence persistence        | 尚无 Attention collector live                                |
| E06 GDELT                     | 未实现                 | E05 依赖已满足                                                    | probe、client、schema、collector、scheduler、API/UI 均未开始 |

## 3. 当前系统能力与不可破坏边界

### 3.1 Foundation 与 Registry

- Python 3.12、FastAPI、SQLAlchemy、Alembic、Pydantic、Typer；
- React 19、TypeScript、Vite、Vitest；
- PostgreSQL 18 与 Docker Compose `db`、`api`、`worker`、`web`；
- immutable Raw/Bronze、Alembic-managed Silver、明确的 Gold boundary；
- Registry YAML 是行政真源，支持严格校验、确定性 checksum、幂等 sync、版本与审计；
- Topic、Alias 与 Source Mapping 分离，不从新关键词或 LLM 自动创建 canonical Topic；
- Coverage、Freshness、Collector Health、Raw integrity 和 Scheduler evidence 是不同事实。

### 3.2 E03 arXiv Research

- 只使用官方 arXiv Atom API，不抓 HTML、不下载 PDF/全文；
- 每个外部响应在解析前进入 immutable Raw；
- Paper、Author、Category、Observation 与 Topic Match 有可追溯 lineage；
- per-mapping cursor、overlap window、限速、retry、递归时间分区和 checkpoint/resume；
- cursor 只在 Raw 与 Silver durable persistence 后前进；
- Paper/Topic 是 many-to-many，Topic Match 由 Registry mapping 明确解释。

历史证据必须保持原义：2026-08-12 至 2026-08-18 原始 soak 因 8 月 15–17 日 missing 而永久失败；2026-08-18 至 2026-08-24 的独立 Recovery 窗口通过 `7/7`。Recovery 不能覆盖原始失败。

### 3.3 E04 GitHub Developer

- 只使用官方 GitHub REST API，不抓 human HTML；
- numeric Repository ID 是持久身份，`full_name` 可变化；
- Search discovery 与 Repository snapshot 分离；
- 每个 HTTP 结果有 Raw provenance，支持 ETag/304；
- snapshot 按真实 UTC 日期不可变并保持 forward-only；
- 缺失日期保持 missing，不插值、不伪造首次观测前 star history；
- GitHub 错误不得修改 arXiv evidence。

### 3.4 E05 Attention Domain

- Attention Source 与 Attention Channel 是不同概念；
- Topic、Event、Entity、Document 与 Observation 是不同领域对象；
- Document 是 evidence，不是 measurement；
- Observation 保存 source、channel、UTC window、metric、unit、definition version 和 provenance；
- 零值与 missing 不同，evidence count 不能替代 measured value；
- source collector 不得自动创建 canonical Event、Entity 或 Topic；
- E05 没有 Public Attention Score、Public Concern Score 或 Trend Score。

## 4. 2026-09-22 实时运行证据

### 4.1 Docker 与数据库

| 检查                             | 结果                                                   |
| -------------------------------- | ------------------------------------------------------ |
| Docker services                  | `db`、`api`、`worker`、`web` 全部 healthy，运行约 5 天 |
| Web                              | `http://localhost:5173`                                |
| API                              | `http://localhost:8000`                                |
| Alembic current/head             | `20260913_0009` / `20260913_0009`                      |
| Live `alembic check`             | `No new upgrade operations detected.`                  |
| `topic_source_coverage` 迁移数据 | `0009` 迁移前后均为 96 行（2026-09-13 验证）           |

`0009` 修复历史 `0005` 造成的三个 check-constraint 双前缀/截断名称，没有重写历史 migration，也没有删除 coverage 数据。

### 4.2 Operations 快照

`signal-observatory ops check --json` 返回 **degraded / exit code 1**。这是当前运营证据，不是代码测试失败。

| 指标                          | 2026-09-22 证据                                                           |
| ----------------------------- | ------------------------------------------------------------------------- |
| Registry                      | degraded；version 2；warning 1                                            |
| arXiv                         | degraded；16,560 papers；42 active mappings；1 failed、3 partial、0 stale |
| arXiv latest run              | 2026-09-22 02:00 UTC，partial；46 Raw responses；1 error                  |
| arXiv latest successful run   | 2026-09-21 02:02 UTC                                                      |
| GitHub                        | degraded；546 known repositories；510 tracked                             |
| GitHub latest run             | 2026-09-22 02:30 UTC，partial；100 Raw responses；1 error                 |
| GitHub latest successful run  | 2026-08-23 06:07 UTC                                                      |
| GitHub snapshot history       | 32 observation dates；latest snapshot 2026-09-22                          |
| GitHub expected missing dates | 377                                                                       |
| Coverage                      | complete 2、partial 3、forward-only 31、unknown 60                        |
| Raw integrity sample          | 100/100 pass；5,055 records available                                     |
| 最近 24h Scheduler            | partial 2；missed 0；late 0；failed 0                                     |

这些数字是 persisted observations 与运行状态，不是 popularity、trend strength 或 coverage percentage。

### 4.3 最近七日 Scheduler 证据

| Window     | arXiv                 | GitHub snapshot     | 说明                                      |
| ---------- | --------------------- | ------------------- | ----------------------------------------- |
| 2026-09-16 | missed                | missed              | Worker 在 due time 不可用                 |
| 2026-09-17 | late / partial        | late / partial      | 约 4 小时后启动                           |
| 2026-09-18 | very late / succeeded | very late / partial | 实际于 9 月 20 日启动                     |
| 2026-09-19 | missing               | missing             | 没有 scheduler execution row              |
| 2026-09-20 | on-time / partial     | late / partial      | GitHub weekly discovery 也为 late/partial |
| 2026-09-21 | on-time / succeeded   | on-time / partial   | 两者均准时启动                            |
| 2026-09-22 | on-time / partial     | on-time / partial   | 两者均准时启动                            |

当前 arXiv rolling continuity：`observed=6/7`，missing `2026-09-19T02:00Z`，missed/interrupted `1`，duplicates `0`，因此为 **FAILED**。

历史 `scheduler-punctuality-v1` 资格仍为：3 个窗口 completed，0 on-time，3 late，最终 **FAILED 0/3**。最近准时窗口是新的正向证据，但不能更改旧合同结果，也尚未构成新的资格序列。

### 4.4 Cursor integrity

`arxiv verify-cursors --json` 当前返回 **failed / exit code 2**：

| 检查                              |                      结果 |
| --------------------------------- | ------------------------: |
| Enabled mappings / parent cursors |                   42 / 42 |
| Parent cursor succeeded           |                        41 |
| Parent cursor failed              | 1 (`ArxivTransportError`) |
| Parent partial / running          |                     0 / 0 |
| Cursor without durable run        |                         0 |
| Cursor without Raw evidence       |                         0 |
| Cursor advanced past failure      |                         0 |
| Unexplained cursor state          |                         4 |

四个异常均为历史 `incremental-part:*` child cursor 缺少 partition root。现有证据不支持“Raw 已损坏”或“cursor 已越过失败”的结论，但 verifier 未通过，因此也不能宣称 lineage 完整。

## 5. Backup / Restore 现状

最近一次 verified backup：

- Backup ID：`20260819T110243Z-97d468`；
- 完成时间：2026-08-19 11:02 UTC；
- migration head：`20260813_0007`；
- Raw objects：746；
- 历史 restore drill：数据库计数、Raw、Registry、lineage 和 API smoke 全部通过。

当前数据库 head 是 `0009`，Raw records 已增至 5,055。因此旧 backup 是历史验收证据，不是当前完整恢复点。

## 6. 自动化质量与发布证据

| 检查                             | 结果                         |
| -------------------------------- | ---------------------------- |
| Ruff lint                        | 通过                         |
| Ruff format                      | 187 files 通过               |
| Mypy                             | 86 source files，无问题      |
| Pytest                           | 199 passed，2 skipped        |
| PostgreSQL connection test       | 通过                         |
| Migration upgrade/downgrade test | 通过                         |
| Live PostgreSQL `alembic check`  | 无 drift                     |
| ESLint                           | 通过                         |
| Prettier                         | 通过                         |
| TypeScript                       | 通过                         |
| Vitest                           | 33 passed                    |
| Vite production build            | 通过；53 modules transformed |
| Docker health                    | 四个服务 healthy             |
| GitHub CI                        | frontend / backend 均通过    |

两个 skip 分别是未配置可选 `TEST_DATABASE_URL` 的外部 PostgreSQL 连接检查，以及 Windows 当前权限不允许创建 symlink 的备份单元测试。迁移和 schema drift 已通过健康 Compose PostgreSQL 另行核验；symlink skip 不是业务断言失败，但也不能替代新的真实 restore drill。

## 7. E06 当前事实边界

E05 已满足 source-neutral domain prerequisite，但仓库当前只有 `collectors/arxiv/` 与 `collectors/github/`。以下均未实现：

- GDELT endpoint capability probe 与受控 fixture；
- GDELT client、query builder、parser 和 collector；
- GDELT-specific Raw index、cursor、schema 和 Alembic migration；
- Registry GDELT mappings；
- GDELT scheduler、Coverage、Operations API/UI；
- 任何 GDELT Media Attention observation。

E06 必须保持：

- Media Attention ≠ Public Attention ≠ Public Concern ≠ Event Importance；
- ArticleList 只能作为 evidence sample，不能用返回条数冒充完整报道量；
- `media_match_count` 必须来自明确定义的 Timeline/raw-count measurement；
- 所有外部响应必须在解析前进入 immutable Raw；
- Topic Match 只能来自 Registry 显式 mapping；
- 不得从 aliases、中文 Topic、LLM 或自动 synonyms 静默构造查询；
- 不抓新闻正文、不绕过 paywall、CAPTCHA 或 rate limit；
- 零结果是合法 observation，missing interval 必须保持 missing；
- 不实现 Trend Score、Momentum、Public Concern 或自动 Event/Entity/Topic discovery。

## 8. 必须交给下一位 GPT 的文件

建议按以下顺序提供：

1. `AGENTS.md`；
2. `docs/acceptance/project-phase-acceptance-report.md`；
3. `README.md`；
4. `docs/acceptance/e04.6-operational-hardening-acceptance.md`；
5. `docs/acceptance/e05-attention-domain-foundation-acceptance.md`；
6. `docs/acceptance/e06-gdelt-global-news-acceptance.md`；
7. `docs/operations/e03-seven-day-scheduler-soak.md`；
8. `docs/operations/scheduler-punctuality.md`；
9. `docs/architecture/overview.md`；
10. `docs/operations/data-health.md`；
11. `docs/operations/coverage-ledger.md`；
12. `docs/operations/backup-restore.md`。

## 9. 给 GPT 的规划指令摘要

下一阶段不要重新实现已经完成的 E00–E05，也不要直接开始生产 GDELT collector。请按以下顺序制定可验收计划：

1. 诊断并修复四个 arXiv partition-root lineage 异常；
2. 修复宿主机长期运行条件，建立新的三窗口 punctuality 和七日 continuity 资格；
3. 为 `0009` 创建并演练当前 recovery unit，完成 off-host copy；
4. 调查 GitHub 持续 partial 与 377 个 missing expected dates，但禁止伪造回填；
5. 然后以小规模官方 API probe 启动 E06，并在生产调度前设置明确的 go/no-go gate。

**最终判断：** 当前工程基线已经审查、发布并通过 CI，具备继续开发的健康基础；但仍不具备直接宣称生产运营可靠或直接上线 E06 的证据。下一阶段的主线应是“先修 lineage 与长期运行，再刷新/异地验证当前备份，最后受控扩展 GDELT”。
