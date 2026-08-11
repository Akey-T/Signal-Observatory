"""Topic Registry operator commands."""

from __future__ import annotations

import asyncio
import getpass
import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from arxiv_collector import (
    ArxivCollectionError,
    ArxivCollectionService,
    ArxivQueryService,
    ArxivRunSummary,
)
from github_collector import (
    GithubCollectionError,
    GithubCollectionService,
    GithubQueryService,
    GithubRunSummary,
)
from observatory_db.coverage_models import CoverageStatus
from observatory_db.models import Topic, TopicStatus
from observatory_db.session import create_database_engine
from observatory_operations import (
    ArxivSoakVerifier,
    CoverageDeriver,
    CoverageQueryService,
    GithubCrossDayVerifier,
    OperationsService,
    RawIntegrityVerifier,
)
from signal_observatory_config import Settings
from topic_registry.diff import RegistryDiff
from topic_registry.loader import TopicRegistryLoader, TopicRegistryValidationError
from topic_registry.models import LoadedRegistry
from topic_registry.queries import TopicQueryService, topic_to_dict
from topic_registry.sync import SyncReport, TopicRegistrySyncService

EXIT_VALIDATION = 1
EXIT_CONFIGURATION = 2
EXIT_DATABASE = 3
DEFAULT_REGISTRY_PATH = Path("config/topics")

app = typer.Typer(help="Signal Observatory operational commands.", no_args_is_help=True)
topics_app = typer.Typer(help="Validate, synchronize, and inspect the curated Topic Registry.")
arxiv_app = typer.Typer(help="Collect and inspect official arXiv metadata.")
github_app = typer.Typer(help="Discover and snapshot public GitHub repositories.")
coverage_app = typer.Typer(help="Rebuild and inspect deterministic data coverage.")
ops_app = typer.Typer(help="Inspect operational health and immutable Raw integrity.")
app.add_typer(topics_app, name="topics")
app.add_typer(arxiv_app, name="arxiv")
app.add_typer(github_app, name="github")
app.add_typer(coverage_app, name="coverage")
app.add_typer(ops_app, name="ops")


def _emit(payload: object, *, as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return
    if isinstance(payload, str):
        typer.echo(payload)
        return
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _fail(message: str, *, code: int, as_json: bool, details: object | None = None) -> NoReturn:
    payload: object = (
        {"ok": False, "error": message, "exit_code": code, "details": details}
        if as_json
        else f"Error: {message}"
    )
    _emit(payload, as_json=as_json)
    raise typer.Exit(code)


def _load(path: Path, *, as_json: bool) -> LoadedRegistry:
    try:
        return TopicRegistryLoader(path).load()
    except TopicRegistryValidationError as error:
        _fail(
            "topic registry validation failed",
            code=EXIT_VALIDATION,
            as_json=as_json,
            details=[issue.model_dump(mode="json") for issue in error.issues],
        )


def _with_session[ResultT](as_json: bool, operation: Callable[[Session], ResultT]) -> ResultT:
    try:
        settings = Settings()
        engine = create_database_engine(settings.database_url)
    except ValidationError as error:
        _fail(
            "invalid application configuration",
            code=EXIT_CONFIGURATION,
            as_json=as_json,
            details=error.errors(include_url=False),
        )
    try:
        with Session(engine) as session:
            return operation(session)
    except SQLAlchemyError as error:
        _fail(
            "database operation failed",
            code=EXIT_DATABASE,
            as_json=as_json,
            details={"type": type(error).__name__, "message": str(error)},
        )
    finally:
        engine.dispose()


@topics_app.command("validate")
def validate_topics(
    registry_path: Annotated[Path, typer.Option("--registry-path")] = DEFAULT_REGISTRY_PATH,
    as_json: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Validate all registry YAML without accessing the database."""

    registry = _load(registry_path, as_json=as_json)
    payload = {
        "ok": True,
        "checksum": registry.checksum,
        "files": len(registry.source_files),
        "categories": len(registry.categories),
        "topics": len(registry.topics),
        "aliases": registry.alias_count,
        "mappings": registry.mapping_count,
        "warnings": [warning.model_dump(mode="json") for warning in registry.warnings],
    }
    if as_json:
        _emit(payload, as_json=True)
    else:
        _emit(
            "Valid Topic Registry\n"
            f"checksum: {registry.checksum}\n"
            f"files/categories/topics/aliases/mappings: "
            f"{payload['files']}/{payload['categories']}/{payload['topics']}/"
            f"{payload['aliases']}/{payload['mappings']}\n"
            f"warnings: {len(registry.warnings)}",
            as_json=False,
        )


@topics_app.command("diff")
def diff_topics(
    registry_path: Annotated[Path, typer.Option("--registry-path")] = DEFAULT_REGISTRY_PATH,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Compare validated YAML with database state without writing anything."""

    registry = _load(registry_path, as_json=as_json)
    registry_diff: RegistryDiff = _with_session(
        as_json, lambda session: TopicRegistrySyncService(session).diff(registry)
    )
    payload = registry_diff.model_dump(mode="json")
    payload["summary"] = registry_diff.summary()
    payload["has_changes"] = registry_diff.has_changes
    if as_json:
        _emit(payload, as_json=True)
        return
    lines = [
        f"Topic Registry diff: {len(registry_diff.changes)} change(s), "
        f"{len(registry_diff.warnings)} warning(s)"
    ]
    lines.extend(
        f"{change.action.value:15} {change.entity_type:10} {change.entity_key}"
        for change in registry_diff.changes
    )
    lines.extend(
        f"warning         {warning.code}: {warning.message}" for warning in registry_diff.warnings
    )
    _emit("\n".join(lines), as_json=False)


@topics_app.command("sync")
def sync_topics(
    registry_path: Annotated[Path, typer.Option("--registry-path")] = DEFAULT_REGISTRY_PATH,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    applied_by: Annotated[str | None, typer.Option("--applied-by")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Apply the validated registry atomically, or preview it with --dry-run."""

    registry = _load(registry_path, as_json=as_json)
    actor = applied_by or getpass.getuser()
    report: SyncReport = _with_session(
        as_json,
        lambda session: TopicRegistrySyncService(session).sync(
            registry, dry_run=dry_run, applied_by=actor
        ),
    )
    payload = report.model_dump(mode="json")
    if as_json:
        _emit(payload, as_json=True)
        return
    state = "dry-run" if report.dry_run else "synchronized"
    version = report.version if report.version is not None else "unchanged"
    _emit(
        f"Topic Registry {state}; changed={report.changed}; version={version}\n"
        f"topics/aliases/categories/mappings: {report.topic_count}/{report.alias_count}/"
        f"{report.category_count}/{report.mapping_count}\n"
        f"checksum: {report.checksum}",
        as_json=False,
    )


@topics_app.command("list")
def list_topics(
    category: Annotated[str | None, typer.Option("--category")] = None,
    status: Annotated[TopicStatus | None, typer.Option("--status")] = None,
    search: Annotated[str | None, typer.Option("--search")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=500)] = 100,
    offset: Annotated[int, typer.Option("--offset", min=0)] = 0,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List synchronized topics with optional filters."""

    def operation(session: Session) -> dict[str, Any]:
        records, total = TopicQueryService(session).list_topics(
            category=category, status=status, search=search, limit=limit, offset=offset
        )
        return {
            "items": [topic_to_dict(topic) for topic in records],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    payload: dict[str, object] = _with_session(as_json, operation)
    if as_json:
        _emit(payload, as_json=True)
        return
    items = payload["items"]
    assert isinstance(items, list)
    lines = [f"{item['slug']:36} {item['status']:10} {item['canonical_name']}" for item in items]
    lines.append(f"{len(items)} shown / {payload['total']} total")
    _emit("\n".join(lines), as_json=False)


@topics_app.command("show")
def show_topic(
    slug: Annotated[str, typer.Argument()],
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show one synchronized topic, including aliases and source mappings."""

    topic: Topic | None = _with_session(
        as_json, lambda session: TopicQueryService(session).get_topic(slug)
    )
    if topic is None:
        _fail("topic not found", code=EXIT_VALIDATION, as_json=as_json, details={"slug": slug})
    payload = topic_to_dict(topic)
    _emit(payload, as_json=as_json)


def _emit_arxiv_summary(summary: ArxivRunSummary, *, as_json: bool) -> None:
    if as_json:
        _emit(summary.model_dump(mode="json"), as_json=True)
        return
    if summary.mode == "dry_run":
        _emit(
            "arXiv backfill dry-run\n"
            f"Topics considered: {summary.topics_considered}\n"
            f"Planned windows: {len(summary.planned_queries)}\n"
            f"Estimated minimum pacing delay: "
            f"{summary.estimated_minimum_delay_seconds:.1f}s\n"
            "No network, database, or Raw writes were performed.",
            as_json=False,
        )
        return
    _emit(
        "arXiv collection complete\n\n"
        f"Status:                 {summary.status}\n"
        f"Topics considered:      {summary.topics_considered}\n"
        f"Mappings executed:      {summary.mappings_executed}\n"
        f"API requests:           {summary.api_requests}\n"
        f"Entries received:       {summary.entries_received}\n"
        f"New papers:             {summary.new_papers}\n"
        f"Updated papers:         {summary.updated_papers}\n"
        f"Existing papers:        {summary.existing_papers}\n"
        f"Topic matches added:    {summary.topic_matches_added}\n"
        f"Errors:                 {summary.errors}\n\n"
        f"Raw payloads preserved: {summary.raw_payloads_preserved}",
        as_json=False,
    )


def _parse_cli_date(value: str | None, *, option: str, as_json: bool) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        _fail(
            f"{option} must use YYYY-MM-DD",
            code=EXIT_VALIDATION,
            as_json=as_json,
            details={option: value},
        )


@arxiv_app.command("backfill")
def arxiv_backfill(
    topics: Annotated[list[str] | None, typer.Option("--topic")] = None,
    all_active: Annotated[bool, typer.Option("--all-active")] = False,
    from_value: Annotated[str | None, typer.Option("--from")] = None,
    until_value: Annotated[str | None, typer.Option("--until")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    max_pages: Annotated[int | None, typer.Option("--max-pages", min=1)] = None,
    page_size: Annotated[int | None, typer.Option("--page-size", min=1, max=2000)] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Backfill bounded date windows for explicit enabled arXiv mappings."""

    if bool(topics) == all_active:
        _fail(
            "choose one or more --topic values or --all-active",
            code=EXIT_VALIDATION,
            as_json=as_json,
        )
    today = datetime.now(UTC).date()
    from_date = _parse_cli_date(from_value, option="--from", as_json=as_json)
    until_date = _parse_cli_date(until_value, option="--until", as_json=as_json)
    first_day = from_date or (today - timedelta(days=730))
    final_day = until_date or today
    if final_day < first_day:
        _fail("--until cannot be before --from", code=EXIT_VALIDATION, as_json=as_json)

    def operation(session: Session) -> ArxivRunSummary:
        settings = Settings()
        service = ArxivCollectionService(session, settings)
        summary = asyncio.run(
            service.backfill(
                topic_slugs=topics if not all_active else None,
                window_from=service.date_start(first_day),
                window_until=service.date_until_exclusive(final_day),
                dry_run=dry_run,
                max_pages=max_pages,
                page_size=page_size,
            )
        )
        if not dry_run:
            CoverageDeriver(session).rebuild()
        return summary

    try:
        summary = _with_session(as_json, operation)
    except ArxivCollectionError as error:
        _fail(str(error), code=EXIT_VALIDATION, as_json=as_json)
    _emit_arxiv_summary(summary, as_json=as_json)


@arxiv_app.command("collect")
def arxiv_collect(
    topics: Annotated[list[str] | None, typer.Option("--topic")] = None,
    max_pages: Annotated[int | None, typer.Option("--max-pages", min=1)] = None,
    page_size: Annotated[int | None, typer.Option("--page-size", min=1, max=2000)] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Run one resumable incremental collection for enabled arXiv mappings."""

    def operation(session: Session) -> ArxivRunSummary:
        summary = asyncio.run(
            ArxivCollectionService(session, Settings()).collect(
                topic_slugs=topics,
                max_pages=max_pages,
                page_size=page_size,
            )
        )
        CoverageDeriver(session).rebuild()
        return summary

    try:
        summary = _with_session(as_json, operation)
    except ArxivCollectionError as error:
        _fail(str(error), code=EXIT_VALIDATION, as_json=as_json)
    _emit_arxiv_summary(summary, as_json=as_json)


@arxiv_app.command("status")
def arxiv_status(
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show persisted collector state without contacting arXiv."""

    payload: dict[str, object] = _with_session(
        as_json, lambda session: ArxivQueryService(session).status()
    )
    if as_json:
        _emit(payload, as_json=True)
        return
    _emit(
        "arXiv collector status\n"
        f"State: {payload['collector_state']}\n"
        f"Last run: {payload['last_run_at']}\n"
        f"Last successful run: {payload['last_successful_run_at']}\n"
        f"Tracked topics/mappings: "
        f"{payload['tracked_topics']}/{payload['tracked_mappings']}\n"
        f"Papers observed: {payload['papers_observed']}\n"
        f"Last run errors: {payload['error_count_last_run']}",
        as_json=False,
    )


@arxiv_app.command("sample")
def arxiv_sample(
    topic: Annotated[str, typer.Option("--topic")],
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 20,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show deterministic matched-paper samples for human mapping review."""

    def operation(session: Session) -> dict[str, object]:
        service = ArxivQueryService(session)
        if not service.topic_exists(topic):
            raise ArxivCollectionError(f"topic not found: {topic}")
        return {"topic_slug": topic, "limit": limit, "items": service.sample(topic, limit=limit)}

    try:
        payload = _with_session(as_json, operation)
    except ArxivCollectionError as error:
        _fail(str(error), code=EXIT_VALIDATION, as_json=as_json)
    _emit(payload, as_json=as_json)


def _emit_github_summary(summary: GithubRunSummary, *, as_json: bool) -> None:
    if as_json:
        _emit(summary.model_dump(mode="json"), as_json=True)
        return
    if summary.mode == "dry_run":
        _emit(
            "GitHub dry-run\n"
            f"Auth configured:       {summary.auth_configured}\n"
            f"Topics considered:     {summary.topics_considered}\n"
            f"Planned operations:    {len(summary.planned_queries)}\n"
            "No network, database, or Raw writes were performed.",
            as_json=False,
        )
        return
    _emit(
        f"GitHub {summary.mode} complete\n\n"
        f"Status:                 {summary.status}\n"
        f"Requests:               {summary.requests_sent}\n"
        f"Raw payloads:           {summary.raw_payloads_preserved}\n"
        f"Repositories received:  {summary.repositories_received}\n"
        f"New/existing repos:     {summary.new_repositories}/{summary.existing_repositories}\n"
        f"Topic matches added:    {summary.topic_matches_added}\n"
        f"Repositories due:       {summary.repositories_due}\n"
        f"200/304/404 responses:  "
        f"{summary.responses_200}/{summary.responses_304}/{summary.responses_404}\n"
        f"Snapshots created:      {summary.snapshots_created}\n"
        f"Errors:                 {summary.errors}",
        as_json=False,
    )


def _github_error(error: GithubCollectionError, *, as_json: bool) -> NoReturn:
    code = (
        EXIT_CONFIGURATION
        if "authentication is not configured" in str(error).casefold()
        else EXIT_VALIDATION
    )
    _fail(str(error), code=code, as_json=as_json)


@github_app.command("discover")
def github_discover(
    topics: Annotated[list[str] | None, typer.Option("--topic")] = None,
    all_active: Annotated[bool, typer.Option("--all-active")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    max_results: Annotated[int | None, typer.Option("--max-results", min=1)] = None,
    max_requests: Annotated[int | None, typer.Option("--max-requests", min=1)] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Discover bounded Repository candidates from explicit enabled mappings."""

    if bool(topics) == all_active:
        _fail(
            "choose one or more --topic values or --all-active",
            code=EXIT_VALIDATION,
            as_json=as_json,
        )

    def operation(session: Session) -> GithubRunSummary:
        summary = asyncio.run(
            GithubCollectionService(session, Settings()).discover(
                topic_slugs=topics if not all_active else None,
                dry_run=dry_run,
                max_results=max_results,
                max_requests=max_requests,
            )
        )
        if not dry_run:
            CoverageDeriver(session).rebuild()
        return summary

    try:
        summary = _with_session(as_json, operation)
    except GithubCollectionError as error:
        _github_error(error, as_json=as_json)
    _emit_github_summary(summary, as_json=as_json)


@github_app.command("snapshot")
def github_snapshot(
    topics: Annotated[list[str] | None, typer.Option("--topic")] = None,
    repositories: Annotated[list[int] | None, typer.Option("--repository")] = None,
    all_tracked: Annotated[bool, typer.Option("--all-tracked")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    max_requests: Annotated[int | None, typer.Option("--max-requests", min=1)] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Record one due daily Snapshot for selected tracked repositories."""

    selections = int(bool(topics)) + int(bool(repositories)) + int(all_tracked)
    if selections != 1:
        _fail(
            "choose --topic, --repository, or --all-tracked",
            code=EXIT_VALIDATION,
            as_json=as_json,
        )

    def operation(session: Session) -> GithubRunSummary:
        summary = asyncio.run(
            GithubCollectionService(session, Settings()).snapshot(
                topic_slugs=topics,
                repository_ids=repositories,
                dry_run=dry_run,
                max_requests=max_requests,
            )
        )
        if not dry_run:
            CoverageDeriver(session).rebuild()
        return summary

    try:
        summary = _with_session(as_json, operation)
    except GithubCollectionError as error:
        _github_error(error, as_json=as_json)
    _emit_github_summary(summary, as_json=as_json)


@github_app.command("status")
def github_status(
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show persisted GitHub collector state without contacting GitHub."""

    payload: dict[str, object] = _with_session(
        as_json, lambda session: GithubQueryService(session, Settings()).status()
    )
    if as_json:
        _emit(payload, as_json=True)
        return
    _emit(
        "GitHub collector status\n"
        f"State: {payload['collector_state']}\n"
        f"Auth configured: {payload['auth_configured']}\n"
        f"Last discovery: {payload['last_discovery_at']}\n"
        f"Last snapshot: {payload['last_snapshot_at']}\n"
        f"Tracked repositories: {payload['tracked_repositories']}\n"
        f"Snapshots: {payload['snapshots']}\n"
        f"Last run errors: {payload['errors_last_run']}",
        as_json=False,
    )


@github_app.command("sample")
def github_sample(
    topic: Annotated[str, typer.Option("--topic")],
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 20,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show deterministic discovered Repository samples for mapping review."""

    def operation(session: Session) -> dict[str, object]:
        service = GithubQueryService(session, Settings())
        if not service.topic_exists(topic):
            raise GithubCollectionError(f"topic not found: {topic}")
        return {"topic_slug": topic, "limit": limit, "items": service.sample(topic, limit=limit)}

    try:
        payload = _with_session(as_json, operation)
    except GithubCollectionError as error:
        _github_error(error, as_json=as_json)
    _emit(payload, as_json=as_json)


@coverage_app.command("rebuild")
def coverage_rebuild(
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Rebuild the Topic-by-Source projection from persisted facts."""

    payload: dict[str, object] = _with_session(
        as_json, lambda session: CoverageDeriver(session).rebuild()
    )
    if as_json:
        _emit(payload, as_json=True)
        return
    _emit(
        "Coverage projection rebuilt\n"
        f"Version: {payload['derivation_version']}\n"
        f"Projections: {payload['projections']}\n"
        f"Created/updated/unchanged/deleted: "
        f"{payload['created']}/{payload['updated']}/{payload['unchanged']}/{payload['deleted']}",
        as_json=False,
    )


@coverage_app.command("list")
def coverage_list(
    source: Annotated[str | None, typer.Option("--source")] = None,
    status: Annotated[CoverageStatus | None, typer.Option("--status")] = None,
    topic: Annotated[str | None, typer.Option("--topic")] = None,
    stale: Annotated[bool | None, typer.Option("--stale/--not-stale")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000)] = 100,
    offset: Annotated[int, typer.Option("--offset", min=0)] = 0,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List persisted coverage projections with deterministic filters."""

    payload: dict[str, object] = _with_session(
        as_json,
        lambda session: CoverageQueryService(session, Settings()).list(
            source=source,
            status=status,
            topic=topic,
            stale=stale,
            limit=limit,
            offset=offset,
        ),
    )
    if as_json:
        _emit(payload, as_json=True)
        return
    items = payload["items"]
    assert isinstance(items, list)
    lines = [f"Coverage Ledger · {payload['total']} result(s)"]
    for item in items:
        assert isinstance(item, dict)
        topic_value = item["topic"]
        assert isinstance(topic_value, dict)
        lines.append(
            f"{topic_value['canonical_name']} · {item['source']} · "
            f"{str(item['coverage_status']).upper()} · "
            f"{item['coverage_start'] or '—'} -> {item['coverage_end'] or '—'}"
        )
    _emit("\n".join(lines), as_json=False)


@coverage_app.command("show")
def coverage_show(
    topic: Annotated[str, typer.Option("--topic")],
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Explain all channel coverage for one canonical Topic."""

    payload = _with_session(
        as_json, lambda session: CoverageQueryService(session, Settings()).topic(topic)
    )
    if payload is None:
        _fail(f"topic not found: {topic}", code=EXIT_VALIDATION, as_json=as_json)
    if as_json:
        _emit(payload, as_json=True)
        return
    lines = [str(payload["topic"]["canonical_name"]), ""]
    for channel in payload["channels"]:
        coverage = channel["coverage"]
        lines.append(f"{channel['label']} / {channel['source']}")
        if coverage is None:
            lines.extend(["Collection: NOT STARTED", ""])
            continue
        lines.extend(
            [
                f"Status: {str(coverage['coverage_status']).upper()}",
                f"Coverage: {coverage['coverage_start'] or '—'} -> "
                f"{coverage['coverage_end'] or '—'}",
                f"Observations: {coverage['observation_count']}",
                f"Latest successful run: {coverage['last_successful_run_at'] or '—'}",
                f"Reason: {coverage['partial_reason'] or '—'}",
                "",
            ]
        )
    _emit("\n".join(lines), as_json=False)


@ops_app.command("verify-raw")
def verify_raw(
    sample: Annotated[int, typer.Option("--sample", min=1, max=10000)] = 100,
    source: Annotated[str | None, typer.Option("--source")] = None,
    full: Annotated[bool, typer.Option("--full")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Verify a bounded Raw sample, or the full lake when explicitly requested."""

    try:
        payload: dict[str, object] = _with_session(
            as_json,
            lambda session: RawIntegrityVerifier(session, Settings().raw_data_path).verify(
                sample=sample, source=source, full=full
            ),
        )
    except ValueError as error:
        _fail(str(error), code=EXIT_VALIDATION, as_json=as_json)
    if as_json:
        _emit(payload, as_json=True)
    else:
        _emit(
            "Raw Integrity\n"
            f"State: {str(payload['state']).upper()}\n"
            f"Mode: {payload['mode']}\n"
            f"Available/checked: {payload['records_available']}/{payload['records_checked']}\n"
            f"Failures: {payload['failures']}\n"
            "No data was modified.",
            as_json=False,
        )
    if payload["state"] == "fail":
        raise typer.Exit(2)


@ops_app.command("check")
def operations_check(
    raw_sample: Annotated[int, typer.Option("--raw-sample", min=1, max=10000)] = 100,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Run the central read-only operational check with documented exit codes."""

    def operation(session: Session) -> dict[str, object]:
        settings = Settings()
        overview = OperationsService(session, settings).overview()
        raw = RawIntegrityVerifier(session, settings.raw_data_path).verify(sample=raw_sample)
        migration = MigrationContext.configure(session.connection()).get_current_revision()
        head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        overall = str(overview["overall_state"])
        if raw["state"] == "fail" or migration != head:
            overall = "failed"
        exit_code = 0 if overall == "healthy" else 1 if overall == "degraded" else 2
        return {
            **overview,
            "overall_state": overall,
            "raw_integrity": raw,
            "database_migration": {
                "state": "current" if migration == head else "outdated",
                "current": migration,
                "head": head,
            },
            "exit_code": exit_code,
        }

    payload: dict[str, Any] = _with_session(as_json, operation)
    if as_json:
        _emit(payload, as_json=True)
    else:
        lines = ["Signal Observatory Operational Check", ""]
        registry = payload["registry"]
        lines.extend(["Registry", str(registry["state"]).upper(), ""])
        for source_health in payload["sources"]:
            label = f"{source_health['label']} / {source_health['display_name']}"
            state = (
                "NOT COLLECTING"
                if not source_health["implemented"]
                else str(source_health["collector_state"]).upper()
            )
            lines.extend([label, state, ""])
        lines.extend(
            [
                "Raw integrity",
                str(payload["raw_integrity"]["state"]).upper(),
                "",
                "Database migration",
                str(payload["database_migration"]["state"]).upper(),
                "",
                "Overall",
                str(payload["overall_state"]).upper(),
            ]
        )
        _emit("\n".join(lines), as_json=False)
    exit_code = int(payload["exit_code"])
    if exit_code:
        raise typer.Exit(exit_code)


@github_app.command("verify-cross-day")
def github_verify_cross_day(
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Verify existing real cross-day Snapshots without triggering collection."""

    payload: dict[str, Any] = _with_session(
        as_json,
        lambda session: GithubCrossDayVerifier(session, Settings()).verify(),
    )
    if as_json:
        _emit(payload, as_json=True)
    else:
        _emit(
            "GitHub Cross-day Verification\n"
            f"Status: {str(payload['status']).upper()}\n"
            f"Observation dates: {payload['observation_date_count']}\n"
            f"Repositories across dates: {payload['repositories_with_multiple_dates']}\n"
            f"Changed/unchanged transitions: "
            f"{payload['changed_transitions']}/{payload['unchanged_transitions']}\n"
            f"{payload['message']}",
            as_json=False,
        )
    exit_code = int(payload["exit_code"])
    if exit_code:
        raise typer.Exit(exit_code)


@arxiv_app.command("verify-soak")
def arxiv_verify_soak(
    days: Annotated[int, typer.Option("--days", min=1, max=90)] = 7,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Verify elapsed scheduler windows without triggering arXiv collection."""

    payload: dict[str, Any] = _with_session(
        as_json,
        lambda session: ArxivSoakVerifier(session, Settings()).verify(days=days),
    )
    if as_json:
        _emit(payload, as_json=True)
    else:
        _emit(
            "arXiv Scheduler Soak Verification\n"
            f"Status: {str(payload['status']).upper()}\n"
            f"Scheduled runs: {payload['actual_scheduled_runs']}/"
            f"{payload['expected_scheduled_windows']}\n"
            f"Succeeded/partial/failed: "
            f"{payload['successful']}/{payload['partial']}/{payload['failed']}\n"
            f"Missing/duplicates/anomalies: "
            f"{payload['missing']}/{payload['duplicate_scheduling']}/"
            f"{payload['cursor_anomalies']}\n"
            f"{payload['message']}",
            as_json=False,
        )
    exit_code = int(payload["exit_code"])
    if exit_code:
        raise typer.Exit(exit_code)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
