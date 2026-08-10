# Signal Observatory 项目阶段性验收说明

> 历史说明：本文记录 E02 验收时点的基线。其第 12 节所列 Web Docker、旧阶段文案和 Registry 固定计数问题已在后续 E02.5 实施中处理；当前运行说明以根 README 为准。

> 验收范围：E00 Project Foundation、E01 Data Infrastructure、E02 Topic Registry
>
> 验收日期：2026-08-10（Australia/Sydney）
>
> 仓库：<https://github.com/Akey-T/Signal-Observatory>
>
> 验收基线：`main` / `26a36c2`，并包含本地尚未提交的 Web Docker 启动修复

## 1. 文档用途

本文件是当前项目状态的可验证快照，供后续 GPT 或开发人员制定下一阶段计划。制定计划时应以本文件列出的已完成功能、范围边界、运行数据和遗留事项为基线，不应重复实施 E00–E02，也不应把尚未进入范围的功能误认为缺陷。

## 2. 验收结论

**结论：E00、E01、E02 的本地工程成果验收通过；发布交付状态为“附带非阻塞整改项通过”。**

- 代码质量门禁全部通过。
- PostgreSQL 空数据库可以从零迁移到当前 Alembic head。
- Docker Compose 可以重新构建并启动全部四个服务，服务均为 healthy。
- Topic Registry 的校验、diff、dry-run、同步幂等性、只读 API 和持久化状态均正常。
- 当前 Registry 为版本 1，共 101 个 Topic、109 个 Alias、15 个 Category、204 个 Source Mapping，警告为 0。
- 当前没有启用任何真实外部 Collector，符合 E00–E02 的范围约束。
- Web 页面是最小平台状态页；E02 不要求 Dashboard 或 Registry 编辑器，因此未展示完整 Topic 浏览界面不构成验收失败。

发布前仍有三项非阻塞事项：

1. `apps/web/Dockerfile` 的启动修复仍在本地工作区，尚未 commit/push；远端 `main` 尚未包含该修复。
2. Web 页脚仍显示 `E00 / E01 foundation`，没有反映 E02 已完成。
3. `docs/topics/topic-registry.md` 仍写“initial registry contains 100 topics”，实际为 101。

## 3. 当前可信基线

### 3.1 Git 状态

- 当前分支：`main`
- 当前提交：`26a36c2 feat: establish Signal Observatory through E02`
- 验收开始时与 `origin/main` 的提交差异：ahead 0 / behind 0
- 验收开始时已有本地修改：`apps/web/Dockerfile`
- 本验收文件是验收过程中新增的文档。

Web Docker 修复内容：

```diff
-CMD ["npm", "run", "dev:web", "--", "--host", "0.0.0.0"]
+CMD ["npm", "run", "dev:web"]
```

根级 `dev:web` 脚本最终调用的 Vite 命令已经包含 host 配置。旧写法重复传入参数，会使 Vite 把第二个地址解释为项目 root，从而导致容器看似运行但首页返回 404。修复后 Web 服务已重新构建并通过健康检查。

### 3.2 工具链

- Python：3.12.13
- Node.js：24.16.0
- npm：11.13.0
- Docker Client：29.6.2
- 项目版本：0.1.0
- 数据库镜像：PostgreSQL 18 Alpine

## 4. 已完成能力

### 4.1 E00 — Project Foundation

- 建立 Python、React/TypeScript/Vite monorepo。
- 建立 API、Web、Worker、PostgreSQL 四个运行组件。
- 提供 Dockerfile、Docker Compose、环境配置和依赖锁定。
- 提供 `/health`、`/ready`、启动校验、数据库重试、结构化日志和优雅关闭。
- 建立 Ruff、mypy、pytest、ESLint、Prettier、Vitest 和生产构建流程。
- 建立 GitHub Actions CI，后端 CI 使用 PostgreSQL 18。
- 建立 README、AGENTS.md、架构文档和 ADR。

### 4.2 E01 — Data Infrastructure

- Bronze：定义通用 Collector contracts，并实现不可变 `LocalRawStore`。
- Raw 记录支持 gzip、SHA-256、字节长度校验、UTC 请求时间、source metadata、collector/schema version、确定性分区路径和原子发布。
- 重复写入同一记录时验证并返回已有记录，不覆盖原始数据。
- Silver：通过 Alembic 建立 sources、topics、topic_aliases、ingestion_runs、ingestion_errors、data_quality_checks 等基础表。
- Ingestion run 支持计数约束、checkpoint 和从 running 到唯一终态的生命周期。
- Gold：只定义可复现指标接口和语义边界，没有提前实现 Trend Score。
- Worker 仍是可健康检查、可优雅关闭的 Collector host，没有真实外部采集逻辑。

### 4.3 E02 — Topic Registry

- `config/topics/*.yaml` 是 curated Topic 的管理事实来源。
- 实现严格 Pydantic schema、未知字段拒绝、跨文件校验和确定性 SHA-256 checksum。
- 实现 Category、Canonical Topic、Alias、Source-specific Mapping。
- Alias normalization 使用 Unicode NFKC、空白规范化和可配置大小写语义，并保留标点。
- 实现重复 slug、重复 canonical name、同 Topic 重复 alias、跨 Topic alias collision、非法 source、缺失 category 等校验。
- 合法 Alias 歧义必须显式 allowlist，并保留 warning、audit 和 data-quality 证据。
- 实现 read-only diff、事务化 sync、dry-run、版本历史、before/after audit log 和 data-quality records。
- 相同 checksum 的重复同步是 no-op，不生成新版本或无意义审计记录。
- YAML 中缺失的数据库 Topic、Alias 或 Mapping 不会被物理删除，而是作为 orphan warning 暴露。
- Topic 只能通过 `deprecated` 退役，历史记录保留。
- 实现 CLI：`validate`、`diff`、`sync`、`list`、`show`，支持 human-readable 与 JSON 输出。
- 实现只读 Topic API，包括搜索、筛选和分页。

## 5. 数据库与 Registry 实测状态

### 5.1 Alembic

- 当前数据库版本：`20260809_0002 (head)`
- 当前 migration head：`20260809_0002 (head)`
- 已存在 migration：
  - `20260809_0001_initial_silver_schema.py`
  - `20260809_0002_topic_registry.py`

空 PostgreSQL 验收过程：

1. 创建独立临时空库 `signal_observatory_acceptance_20260810`。
2. 执行 `alembic upgrade head`。
3. 成功依次应用 `20260809_0001` 和 `20260809_0002`。
4. 验证 `alembic_version = 20260809_0002`，public schema 共 11 张表。
5. 验收完成后删除该临时数据库，没有修改或清空项目现有数据库。

### 5.2 Topic Registry

| 指标              |                                                             实测值 |
| ----------------- | -----------------------------------------------------------------: |
| Registry version  |                                                                  1 |
| Source YAML files |                                                                  6 |
| Categories        |                                                                 15 |
| Topics            |                                                                101 |
| Active Topics     |                                                                101 |
| Aliases           |                                                                109 |
| Source Mappings   |                                                                204 |
| Warnings          |                                                                  0 |
| Checksum          | `f2deee8290c51b0842a8e123626465aa004f9850e136ead93d95258314152394` |
| Last synced at    |                                      `2026-08-09T11:26:24.745138Z` |

运行时校验结果：

```text
Valid Topic Registry
files/categories/topics/aliases/mappings: 6/15/101/109/204
warnings: 0
```

运行时 diff：

```text
Topic Registry diff: 0 change(s), 0 warning(s)
```

运行时 dry-run：

```text
Topic Registry dry-run; changed=False; version=unchanged
topics/aliases/categories/mappings: 101/109/15/204
```

这证明当前 YAML 与数据库运行时投影一致，重复应用不会产生新版本。

## 6. 服务与 API 验收

### 6.1 Docker Compose

`docker compose up -d --build` 成功，以下服务均处于 running/healthy：

| 服务       | 端口       | 状态    |
| ---------- | ---------- | ------- |
| PostgreSQL | 5432       | healthy |
| API        | 8000       | healthy |
| Web        | 5173       | healthy |
| Worker     | 无宿主端口 | healthy |

### 6.2 HTTP 实测

- `GET /health`：200，API healthy，版本 0.1.0。
- `GET /ready`：200，API ready，版本 0.1.0。
- `GET /api/topic-registry/status`：200，返回上述 Registry v1 计数与 checksum。
- `GET /api/topics?limit=1&offset=0`：200，total 为 101，并返回 Topic、Category、Alias 与 Source Mapping。
- `GET http://localhost:5173/`：200，返回 Signal Observatory Web 应用入口。

当前只读 API：

- `GET /api/topics?category=&status=&search=&limit=&offset=`
- `GET /api/topics/{slug}`
- `GET /api/categories`
- `GET /api/topic-registry/status`
- `GET /health`
- `GET /ready`

### 6.3 浏览器视觉与控制台复核

重新构建后在浏览器打开 `http://localhost:5173/`，页面标题为 `Signal Observatory`，DOM 正常渲染 Hero、API 0.1.0 在线状态、Bronze/Silver/Gold 架构区块和范围页脚。页面截图未发现明显重叠、截断或异常空白；浏览器控制台没有 error 或 warning，只有 Vite 连接调试信息和 React DevTools 开发提示。

本项同时确认了一个展示偏差：页面仍显示 `Foundation online` 和 `E00 / E01 foundation`。它不影响 E02 功能验收，但应按第 12 节更新，以免项目状态页低估当前里程碑。

## 7. 质量门禁结果

### 7.1 Python

| 检查                              | 结果                             |
| --------------------------------- | -------------------------------- |
| `python -m ruff check .`          | 通过                             |
| `python -m ruff format --check .` | 通过，74 files already formatted |
| `python -m mypy apps packages db` | 通过，37 source files 无问题     |
| `python -m pytest`                | 57 passed，1 skipped             |
| PostgreSQL 专用测试补跑           | 1 passed                         |

默认 pytest 未设置 `TEST_DATABASE_URL`，因此 PostgreSQL 连接测试按设计跳过。验收随后设置该变量连接正在运行的 PostgreSQL，单独执行该测试并通过。因此本次收集到的 58 个 Python 测试场景均已有通过证据，但不是在同一个 pytest invocation 中完成。

### 7.2 Frontend

| 检查                   | 结果                             |
| ---------------------- | -------------------------------- |
| `npm run lint`         | 通过                             |
| `npm run format:check` | 通过                             |
| `npm run typecheck`    | 通过                             |
| `npm run test`         | 1 test passed                    |
| `npm run build`        | 通过，Vite production build 成功 |

### 7.3 Docker 与数据库

| 检查                             | 结果                  |
| -------------------------------- | --------------------- |
| `docker compose config --quiet`  | 通过                  |
| `docker compose up -d --build`   | 通过                  |
| 四个 Compose 服务健康检查        | 全部通过              |
| 当前数据库 Alembic current/head  | 一致，`20260809_0002` |
| 独立空 PostgreSQL 全量 migration | 通过                  |
| Topic validate/diff/dry-run      | 全部通过              |

## 8. E02 Definition of Done 对照

|   # | 验收项                  | 状态 | 主要证据                                             |
| --: | ----------------------- | ---- | ---------------------------------------------------- |
|   1 | Registry YAML schema    | 通过 | `config/topics/` 与严格 Pydantic models              |
|   2 | Topic Category          | 通过 | 15 categories、层级表与 API                          |
|   3 | Canonical Topic         | 通过 | 101 canonical topics                                 |
|   4 | Alias                   | 通过 | 109 aliases 与 normalization                         |
|   5 | Source Mapping          | 通过 | 204 mappings                                         |
|   6 | Alias collision 检测    | 通过 | invalid fixture 与 loader test                       |
|   7 | Collision allowlist     | 通过 | warning、audit、quality test                         |
|   8 | Registry validation     | 通过 | CLI validate 与完整测试                              |
|   9 | Deterministic checksum  | 通过 | 顺序无关与内容变化测试                               |
|  10 | Diff                    | 通过 | CLI/API service；运行时 0 changes                    |
|  11 | Dry-run                 | 通过 | 不写库测试；运行时 changed=False                     |
|  12 | Sync                    | 通过 | 事务化同步及运行时 v1                                |
|  13 | Sync idempotent         | 通过 | 第二次同步 no-op 测试及运行时 dry-run                |
|  14 | Transaction rollback    | 通过 | 强制异常与 dry-run rollback 测试                     |
|  15 | Registry version        | 通过 | v1 与版本变更测试                                    |
|  16 | Audit log               | 通过 | before/after 与 review audit 测试                    |
|  17 | YAML 消失不误删 Topic   | 通过 | orphan warning/retention 测试                        |
|  18 | CLI                     | 通过 | validate/diff/sync/list/show、JSON、exit codes       |
|  19 | Read-only API           | 通过 | list/detail/search/filter/pagination/404/status 测试 |
|  20 | 至少 100 个高质量 Topic | 通过 | 101 topics，warnings=0                               |
|  21 | Tests                   | 通过 | 全部 58 个 Python 场景有通过证据；前端 1 passed      |
|  22 | Lint                    | 通过 | Ruff 与 ESLint                                       |
|  23 | Typecheck               | 通过 | strict mypy 与 TypeScript                            |
|  24 | 空数据库 migrations     | 通过 | 独立空 PostgreSQL 实测到 head                        |
|  25 | README                  | 通过 | 启动、CLI、API、架构和范围说明已存在                 |
|  26 | Architecture docs       | 通过 | Bronze/Silver/Gold 与 Registry control plane         |
|  27 | ADR                     | 通过 | ADR-006、ADR-007、ADR-008 已存在                     |
|  28 | 无核心 TODO/placeholder | 通过 | 扫描未发现核心 TODO；Worker 明确是范围内 skeleton    |

## 9. 关键行为场景证据

原 E02 验收要求中的六个案例均有自动化证据：

- Case A，新增 Topic：空数据库 full sync 测试创建 Topic。
- Case B，新增或更新 Alias：version change 测试覆盖 Alias add/update。
- Case C，未 allowlist 的跨 Topic Alias 冲突：validate 失败并返回 `ALIAS_COLLISION`。
- Case D，显式 allowlist：validate 成功，同时创建可见 warning、audit 和 quality 信息。
- Case E，从 YAML 移除 Topic：产生 orphan warning，数据库 Topic 保留。
- Case F，显式 `deprecated`：写入退役状态和时间，历史实体保留。

## 10. 数据与架构不变量

后续计划和实现不得破坏以下约束：

1. Raw/Bronze 数据不可变，不得原地编辑。
2. 每次 ingestion 必须可追踪且幂等。
3. 所有 schema 变化必须新增 Alembic migration，不得修改已应用 migration。
4. 时间统一使用 UTC。
5. Gold 指标必须能从持久化输入和版本化定义重算。
6. `config/topics/` 是 curated Registry 的行政事实来源，数据库只是运行时投影。
7. 新观察到的关键词不得自动成为 Canonical Topic。
8. Alias 歧义必须暴露，不得静默猜测归属。
9. 已有关联历史的 Topic 不得删除，只能显式 deprecated。
10. Source-specific 查询逻辑不得泄漏到通用 Topic 模型。
11. LLM 不得修改 Raw observations，也不得静默修改 curated Registry。
12. 优先使用官方 API 或 feed；不得绕过认证、CAPTCHA、rate limit 或反爬机制。

## 11. 已知限制与明确未实现范围

以下内容当前未实现，而且是 E00–E02 的明确范围外事项：

- 真实 arXiv、GitHub、Hacker News、Wikipedia Collector
- 自动 Topic Discovery
- LLM 自动分类或摘要
- Semantic embedding、vector search、fuzzy/regex matching
- Trend Score、聚合和完整 Gold persistence
- 大规模 Dashboard、Web Registry Editor
- Authentication、用户、角色和审批 UI
- 云基础设施、Kafka、Spark、Airflow、Kubernetes

这些缺失不应被记录为当前阶段失败。

## 12. 非阻塞整改项

### P1 — 完成可复现交付

将已经验收通过的 `apps/web/Dockerfile` 修复提交并推送。否则从当前远端 `main` 重新 clone 后，Web 容器仍可能出现首页 404。

### P2 — 更新 Web 阶段文案

当前页脚为：

```text
E00 / E01 foundation · No external collectors enabled
```

建议改为能够体现 E02，例如：

```text
E00 / E01 / E02 · Topic Registry online · No external collectors enabled
```

状态区域可以补充只读 Registry 信息，例如 `Registry v1 · 101 topics · 0 warnings`。这属于状态展示，不应扩展成 E02 范围外的编辑器或大型 Dashboard。

### P2 — 修正文档计数

将 `docs/topics/topic-registry.md` 的“100 topics”更新为实际的 101，或改写为不易过期的表述并引用 Registry status。

### P3 — 本机命令行环境说明

本次 Codex shell 没有自动找到 Docker CLI，但 Docker Desktop 和 CLI 实际已安装。通过 Docker CLI 的绝对路径并为当前进程补充 Docker tools 目录后，构建和验收成功。可在本地启动文档中提醒：安装 Docker Desktop 后重新打开终端，并先验证 `docker --version` 与 `docker compose version`。

## 13. 给下一阶段规划 GPT 的输入

### 13.1 开始规划前应先关闭的交付事项

1. 提交 Web Docker 启动修复。
2. 更新 Web 的 E02 状态文案。
3. 修正 Topic Registry 文档计数。
4. 重新运行受影响的前端检查和 Compose smoke test。
5. commit 并 push，确保远端基线可复现。

### 13.2 下一推荐 Epic

原阶段要求指定下一推荐 Epic 为：

```text
E03 — arXiv Collector
```

下一 GPT 应先输出 E03 的窄范围实施计划，不应同时启动 GitHub、Hacker News、Wikipedia、Trend Score、Topic Discovery、LLM 或大型 Dashboard。

E03 计划至少应围绕以下已存在接口和不变量展开：

- 使用官方 arXiv 机器接口/feed，并遵守 rate limit 和使用条款。
- 所有请求结果先以不可变 Raw/Bronze 记录持久化。
- 每次运行创建 ingestion run，记录 checkpoint、计数、错误和 collector version。
- 重试和重复运行必须幂等，不得产生重复 Silver observations。
- arXiv 实体与 Topic 通过稳定 `topic_id` 和显式 arXiv Source Mapping 关联。
- 原始记录与规范化结果分离；解析或映射修订不得重写 Raw。
- 新表或约束必须通过新 Alembic migration 引入。
- 指标、Trend Score 和其他 Collector 继续保持范围外。
- 为离线 fixture、分页/checkpoint、重试、限流、重复采集和失败恢复编写测试。

### 13.3 规划时应参考的核心文件

- `AGENTS.md`
- `README.md`
- `docs/architecture/overview.md`
- `docs/topics/topic-registry.md`
- `docs/metrics/gold-interface.md`
- `packages/collector-core/`
- `packages/topic-registry/`
- `db/src/observatory_db/`
- `db/migrations/versions/`
- `config/topics/`
- `.github/workflows/ci.yml`

## 14. 建议的验收复现命令

在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy apps packages db
.\.venv\Scripts\python.exe -m pytest
npm run lint
npm run format:check
npm run typecheck
npm run test
npm run build
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose exec api signal-observatory topics validate
docker compose exec api signal-observatory topics diff
docker compose exec api signal-observatory topics sync --dry-run --applied-by acceptance
```

运行后检查：

- Web：<http://localhost:5173>
- API：<http://localhost:8000>
- OpenAPI：<http://localhost:8000/docs>
- Registry status：<http://localhost:8000/api/topic-registry/status>

## 15. 最终判定

E00–E02 已形成一个可运行、可测试、可迁移、可审计、可重复同步的数据工程基础。当前本地工作区具备进入 E03 规划阶段的技术条件。开始 E03 实施前，应先完成第 12 节的交付整改并将验收后的基线推送到 GitHub。
