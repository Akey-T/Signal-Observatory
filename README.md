# Signal Observatory

E04.6 hardens durable scheduling and arXiv incremental recovery. Scheduler continuity, dispatch
punctuality, and collector outcomes are now separate persisted facts; broad arXiv incremental
queries recursively partition into resumable child windows. Operator guidance is in
[`docs/operations/scheduler-punctuality.md`](docs/operations/scheduler-punctuality.md).

E05 Attention Domain Foundation is implemented and accepted as a source-neutral domain boundary.
It persists Attention Documents, measured Observations, and Evidence links while keeping Event and
Entity canonicalization contract-only. No Public Attention source is live yet; E06 GDELT remains
implementation-not-started until its bounded probe and collector acceptance.

E04.5B recovery-unit commands remain documented in
[`docs/operations/backup-restore.md`](docs/operations/backup-restore.md). A typical local cycle is:

```powershell
signal-observatory backup create --label "operator checkpoint" --json
signal-observatory backup list --json
signal-observatory backup verify <backup-id> --full --json
signal-observatory backup drill <backup-id> --json
```

The Operations page reports the latest verified backup and restore drill. It is read-only. Backups
under `data/backups/` are intentionally ignored by Git and a same-disk copy is not sufficient as
the only disaster-recovery copy.

Signal Observatory 是一个长期运行的数据工程与趋势研究项目。它保存公开机器接口中的技术生态观测，构建可追溯、可重复计算的历史序列，用于研究技术从 Research → Developer Adoption → Community Attention → Public Attention 的传播过程。

当前仓库已完成并验收 **E00–E05**，并完成 E04.5B recovery-unit 验收。E04 GitHub 跨日验收已经通过；E03 调度恢复窗口已于
`2026-08-18` 至 `2026-08-24` 连续 7 天通过，但该结论只证明连续性。E04.6 的实现门禁已经完成，
其 `≤300s` 准时性资格最近 3 个真实计划窗口为 `FAILED 0/3`（均迟到），当前不得标记为通过。Trend Score、
AI 摘要、自动 Topic discovery 和业务趋势 Dashboard 仍不在当前范围内。

## 已实现

- Python 3.12、FastAPI、SQLAlchemy、Alembic、Pydantic、Typer
- React 19、TypeScript、Vite、Vitest
- PostgreSQL、Docker Compose、API/Web/Worker 三个服务
- 不可变 Bronze 原始记录与 Alembic 管理的 Silver schema
- YAML 管理的 Topic Registry：分类、canonical topics、aliases、source mappings
- 严格 schema、跨文件唯一性、alias 冲突检测、确定性 checksum
- 只读 diff、事务 sync、dry-run、版本历史、审计日志与数据质量记录
- CLI 与只读 Topic API
- Registry Overview、Topic Explorer 与 Topic Detail 三个只读 Web 入口
- 动态 Registry Health、确定性 Featured Topics、Category Universe 与未来 Observation slots
- 官方 arXiv API 元数据采集、不可变 Raw 响应、规范化 Paper/Author/Category 与可解释 Topic Match
- 可恢复历史 backfill、每 mapping 增量 cursor、每日 Worker 调度、受控 retry/rate limit 与 403 停止策略
- Research Observation API、collector status、人工 mapping sample，以及 Topic Detail 的 live/degraded/zero-data 状态
- 官方 GitHub REST API 认证客户端、Raw-first Repository discovery、numeric Repository identity、可解释 Topic match
- 每日不可变 Repository Snapshot、ETag/304、Search/Core budget、保守限流与独立 weekly discovery/daily snapshot 调度
- Developer Observation API、collector status、Repository evidence 列表，以及真实 live/degraded/zero-data 状态
- Topic × Source Coverage Ledger，确定性区分 Complete、Partial、Forward only、Empty 与 Unknown
- 统一的 Collector Health、Freshness、Data Quality 与 Observatory overall state
- 只读 Raw integrity、GitHub 跨日和 arXiv 七天调度验收工具
- 调度连续性与准时性分离、`ON_TIME/LATE/MISSED/INTERRUPTED` 时间证据和 3 窗口资格门禁
- arXiv 大增量查询递归时间分区、父/子 checkpoint 恢复和只读 cursor lineage 验证
- Attention Domain Foundation：Source/Channel、Document、Observation、Evidence 合同与最小持久化
- `/operations` 工程运营页面、Coverage Matrix 与 Topic Detail 覆盖摘要

## 快速启动

前置条件是 Python 3.12+、Node.js 24+；完整服务需要 Docker Desktop。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
npm ci
docker compose up --build
```

服务地址：Web <http://localhost:5173>、API <http://localhost:8000>、OpenAPI <http://localhost:8000/docs>。

Web 路由：

- `/`：Registry Overview，动态展示 Registry 统计、3 个跨领域 Featured Topics、30 个 Supporting Topics、Topic Universe 和 Registry Health。
- `/topics`：Topic Explorer，支持 Topic/Alias 搜索、Category/Status/Source 筛选、URL query state 和分页。
- `/topics/:slug`：Topic Detail，展示 Canonical Topic、Aliases、Monitoring Priority、可读 Source Mapping，以及持久化 arXiv Research / GitHub Developer observations。
- `/operations`：Operations，展示 Collector Health、Freshness、Data Quality、Coverage Matrix 与真实缺口。

Web 只将拥有真实成功 cursor 的 arXiv mapping 标记为 **Research Live**，只将拥有真实成功 Repository Snapshot 的 GitHub mapping 标记为 **Developer Live**；失败后的历史数据以 **Degraded** 状态继续可读。`Configured` 仍只表示 Registry 中存在 Source Mapping。Hacker News 和 Wikipedia 为 **Not collecting yet**，页面不会展示没有持久化 Observation 支撑的 Trend、Growth、Momentum 或 Popularity。

## Topic Registry

`config/topics/*.yaml` 是 curated topics 的管理源。数据库是同步后的运行时投影，不应手工修改来替代 YAML 评审。

```powershell
signal-observatory topics validate
signal-observatory topics diff
signal-observatory topics sync --dry-run
signal-observatory topics sync --applied-by your-name
signal-observatory topics list --status active --search MCP
signal-observatory topics show model-context-protocol --json
```

在未安装 console script 的环境中，可使用：

```powershell
python -m signal_observatory_cli.main topics validate --json
```

CLI 退出码：`0` 成功，`1` registry 校验或查询失败，`2` 配置失败，`3` 数据库失败。同步前必须运行 `alembic upgrade head`。重复同步相同 checksum 不创建新版本或审计记录。

只读 API：

- `GET /api/topics?category=&status=&search=&limit=&offset=`
- `GET /api/topics/{slug}`
- `GET /api/categories`
- `GET /api/topic-registry/status`
- `GET /api/sources/arxiv/status`
- `GET /api/topics/{slug}/research`
- `GET /api/sources/github/status`
- `GET /api/topics/{slug}/development`

完整维护手册见 [Topic Registry 文档](docs/topics/topic-registry.md)。

## arXiv Research Collector

采集器只使用 Registry 中显式启用的 arXiv mapping 和官方 Atom API。默认单连接、请求起始时间至少间隔 3 秒；每个响应在解析前先进入不可变 Raw。E03 不抓取 HTML，不下载 PDF/全文，也不使用 LLM 或 embedding 判断 Topic。

```powershell
signal-observatory arxiv status --json
signal-observatory arxiv backfill --topic model-context-protocol --from 2026-07-01 --until 2026-08-10 --dry-run
signal-observatory arxiv collect --topic model-context-protocol --json
signal-observatory arxiv sample --topic model-context-protocol --limit 20 --json
signal-observatory arxiv cursor-audit --json
signal-observatory arxiv verify-cursors --json
```

backfill 与 incremental 都有 per-mapping checkpoint；大结果集会递归拆分为有独立 cursor 的子窗口，
只有 Raw 与 Silver 成功持久化后父 cursor 才会前进。详细策略见
[arXiv source 文档](docs/sources/arxiv.md)，实测数据见 [Pilot 报告](docs/data/arxiv-pilot-report.md)。

## GitHub Developer Collector

Collector 只读取 Registry 中显式启用的 GitHub mapping，并使用官方 REST API。稳定身份是
GitHub numeric Repository ID；`owner/repo` 可以随 rename/transfer 更新。第一次真实快照是
历史覆盖起点，此前的每日 Stars 不会被伪造。

先复制 `.env.example` 为被 Git 忽略的 `.env`，设置只读公开 Repository metadata 所需的
`GITHUB_TOKEN`，再重建服务。Token 不会进入 Raw、日志、API 或前端。缺少 Token 时状态明确为
`not_configured`，默认不会静默执行匿名高流量采集。

```powershell
signal-observatory github status --json
signal-observatory github discover --topic model-context-protocol --dry-run --json
signal-observatory github discover --topic model-context-protocol --max-results 10 --max-requests 5 --json
signal-observatory github sample --topic model-context-protocol --limit 20 --json
signal-observatory github snapshot --topic model-context-protocol --json
```

Discovery 默认每周执行、Snapshot 默认每天执行；两者使用独立 Search/Core budget。详细策略见
[GitHub source 文档](docs/sources/github.md)。E04 认证 Pilot、人工复核和真实跨日 Snapshot 验收均已完成；
GitHub 历史仍诚实地从首次观测日起保持 `FORWARD_ONLY`。

## Operations 与 Coverage Ledger

Operations 将“采集器最近是否正常运行”“数据是否新鲜”“历史覆盖是否完整”作为三个独立概念。
Coverage 仅由持久化 Observation、Cursor 与 Run 确定性派生；重复 rebuild 不改变相同事实，GitHub
历史从首次真实 Snapshot 开始并始终标为 `FORWARD_ONLY`。缺失日期不会被插值，页面也不展示没有
严格分母定义的完整率或健康百分比。

```powershell
signal-observatory coverage rebuild --json
signal-observatory coverage list --source arxiv --status partial
signal-observatory coverage show --topic model-context-protocol --json
signal-observatory ops check --json
signal-observatory ops verify-raw --sample 100 --json
signal-observatory github verify-cross-day --json
signal-observatory arxiv verify-soak --days 7 --json
signal-observatory scheduler status --json
signal-observatory scheduler verify-punctuality --json
```

`ops check` 退出码：`0` healthy/acceptable，`1` degraded，`2` failed/action required，`3`
configuration/database failure。`github verify-cross-day`、`arxiv verify-soak` 和
`scheduler verify-punctuality` 都是只读验收工具；时间窗口不足时返回 `PENDING`，不会触发采集或
修改数据。手工采集不能满足 scheduler 资格，collector 的 `partial/failed` 也不会改变已记录的启动延迟。

只读 API：

- `GET /api/operations`
- `GET /api/coverage?source=&status=&topic=&limit=&offset=`
- `GET /api/topics/{slug}/coverage`

详细语义见 [Data Health](docs/operations/data-health.md) 与
[Coverage Ledger](docs/operations/coverage-ledger.md)。

## 数据库与质量检查

```powershell
alembic upgrade head
python -m ruff check .
python -m ruff format --check .
python -m mypy apps packages config db collectors
python -m pytest
npm run lint
npm run format:check
npm run typecheck
npm run test
npm run build
```

PostgreSQL 专用测试在 `TEST_DATABASE_URL` 存在时运行，CI 提供 PostgreSQL 18。其余集成测试也会从空 SQLite 数据库执行完整 Alembic migration，不使用 `create_all()` 替代正式迁移。

## 数据架构

```text
Curated YAML → validate/diff → transactional Registry sync → Silver Topics
Public Source → Collector → Raw/Bronze → Normalization → Silver Observations
Silver → Aggregation → Gold → Analytics → API → UI
```

Topic Registry 只定义观测对象及各来源的显式查询映射。它不执行网络请求，不从关键词自动创建 canonical Topic，也不会删除数据库中的历史 Topic。YAML 中移除的数据库实体会作为 orphan warning 保留；明确退役必须将 status 改为 `deprecated`。

详细设计见 [架构总览](docs/architecture/overview.md) 与 [ADR](docs/adr/)。下一步规划必须同时考虑
E04.6 三个真实准时窗口的未决资格和独立的产品 Epic；未决资格不得用手工运行提前关闭。
