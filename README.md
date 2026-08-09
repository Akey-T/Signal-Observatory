# Signal Observatory

Signal Observatory 是一个长期运行的数据工程与趋势研究项目。它保存公开机器接口中的技术生态观测，构建可追溯、可重复计算的历史序列，用于研究技术从 Research → Developer Adoption → Community Attention → Public Attention 的传播过程。

当前仓库完成 **E00 Project Foundation**、**E01 Data Infrastructure** 与 **E02 Topic Registry**。真实数据采集、Trend Score、AI 摘要、自动 topic discovery 和完整 Dashboard 仍不在当前范围内。

## 已实现

- Python 3.12、FastAPI、SQLAlchemy、Alembic、Pydantic、Typer
- React 19、TypeScript、Vite、Vitest
- PostgreSQL、Docker Compose、API/Web/Worker 三个服务
- 不可变 Bronze 原始记录与 Alembic 管理的 Silver schema
- YAML 管理的 Topic Registry：分类、canonical topics、aliases、source mappings
- 严格 schema、跨文件唯一性、alias 冲突检测、确定性 checksum
- 只读 diff、事务 sync、dry-run、版本历史、审计日志与数据质量记录
- CLI 与只读 Topic API

## 快速启动

前置条件是 Python 3.12+、Node.js 24+；完整服务需要 Docker Desktop。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
npm ci
docker compose up --build
```

服务地址：Web <http://localhost:5173>、API <http://localhost:8000>、OpenAPI <http://localhost:8000/docs>。

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

完整维护手册见 [Topic Registry 文档](docs/topics/topic-registry.md)。

## 数据库与质量检查

```powershell
alembic upgrade head
python -m ruff check .
python -m ruff format --check .
python -m mypy apps packages config db
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

详细设计见 [架构总览](docs/architecture/overview.md) 与 [ADR](docs/adr/)。下一 Epic 是 **E03 arXiv Collector**。
