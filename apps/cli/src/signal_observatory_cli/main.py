"""Topic Registry operator commands."""

from __future__ import annotations

import asyncio
import getpass
import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from arxiv_collector import ArxivCollectionError, ArxivCollectionService, ArxivRunSummary
from observatory_db.models import Topic, TopicStatus
from observatory_db.session import create_database_engine
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
app.add_typer(topics_app, name="topics")
app.add_typer(arxiv_app, name="arxiv")


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

    def operation(session: Session) -> dict[str, object]:
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
        return asyncio.run(
            service.backfill(
                topic_slugs=topics if not all_active else None,
                window_from=service.date_start(first_day),
                window_until=service.date_until_exclusive(final_day),
                dry_run=dry_run,
                max_pages=max_pages,
                page_size=page_size,
            )
        )

    try:
        summary = _with_session(as_json, operation)
    except ArxivCollectionError as error:
        _fail(str(error), code=EXIT_VALIDATION, as_json=as_json)
    _emit_arxiv_summary(summary, as_json=as_json)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
