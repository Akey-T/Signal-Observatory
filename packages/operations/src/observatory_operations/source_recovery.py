"""Registered source adapters used by backup, Raw integrity, and restore."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import InstrumentedAttribute, Session

from collector_core import DataIntegrityError, LocalRawStore
from observatory_db.arxiv_models import (
    ArxivPaperObservation,
    ArxivRawResponse,
    ArxivTopicMatch,
)
from observatory_db.github_models import (
    GithubRawResponse,
    GithubRepositorySnapshot,
    GithubTopicRepositoryMatch,
)
from observatory_db.models import IngestionRun, TopicSourceMapping

LineageSampler = Callable[[Session, Path], list[dict[str, str]]]


@dataclass(frozen=True, slots=True)
class SourceRecoveryAdapter:
    """Describe the persisted recovery surfaces owned by one implemented source."""

    name: str
    raw_model: Any
    entity_table: str
    match_table: str
    raw_table: str
    lineage_sampler: LineageSampler
    snapshot_table: str | None = None
    observation_date_column: InstrumentedAttribute[Any] | None = None


def _verify_raw_pointer(raw_root: Path, source: str, raw_path: str, checksum: str) -> None:
    store = LocalRawStore(raw_root)
    path = store.resolve_key(raw_path, source=source)
    record = store.load(path)
    if record.sha256 != checksum:
        raise DataIntegrityError("lineage checksum differs from the Raw metadata sidecar")
    store.read(record)


def _arxiv_lineage_samples(session: Session, raw_root: Path) -> list[dict[str, str]]:
    samples: list[dict[str, str]] = []
    rows = session.execute(
        select(
            ArxivTopicMatch,
            ArxivPaperObservation,
            ArxivRawResponse,
            TopicSourceMapping,
            IngestionRun,
        )
        .join(
            ArxivPaperObservation,
            ArxivPaperObservation.paper_id == ArxivTopicMatch.paper_id,
        )
        .join(ArxivRawResponse, ArxivRawResponse.id == ArxivPaperObservation.raw_response_id)
        .join(TopicSourceMapping, TopicSourceMapping.id == ArxivTopicMatch.source_mapping_id)
        .join(IngestionRun, IngestionRun.run_id == ArxivPaperObservation.ingestion_run_id)
        .order_by(ArxivTopicMatch.id)
        .limit(10)
    ).all()
    for match, observation, raw, mapping, run in rows:
        _verify_raw_pointer(raw_root, "arxiv", raw.raw_path, raw.payload_checksum)
        samples.append(
            {
                "match_id": str(match.id),
                "observation_id": str(observation.id),
                "mapping_id": str(mapping.id),
                "run_id": str(run.run_id),
                "raw_id": str(raw.id),
                "raw_key": raw.raw_path,
            }
        )
    return samples


def _github_lineage_samples(session: Session, raw_root: Path) -> list[dict[str, str]]:
    samples: list[dict[str, str]] = []
    rows = session.execute(
        select(
            GithubRepositorySnapshot,
            GithubTopicRepositoryMatch,
            GithubRawResponse,
            TopicSourceMapping,
            IngestionRun,
        )
        .join(
            GithubTopicRepositoryMatch,
            GithubTopicRepositoryMatch.repository_id == GithubRepositorySnapshot.repository_id,
        )
        .join(GithubRawResponse, GithubRawResponse.id == GithubRepositorySnapshot.raw_response_id)
        .join(
            TopicSourceMapping,
            TopicSourceMapping.id == GithubTopicRepositoryMatch.source_mapping_id,
        )
        .join(IngestionRun, IngestionRun.run_id == GithubRepositorySnapshot.ingestion_run_id)
        .order_by(GithubRepositorySnapshot.id)
        .limit(10)
    ).all()
    for snapshot, match, raw, mapping, run in rows:
        _verify_raw_pointer(raw_root, "github", raw.raw_path, raw.payload_checksum)
        samples.append(
            {
                "snapshot_id": str(snapshot.id),
                "match_id": str(match.id),
                "mapping_id": str(mapping.id),
                "run_id": str(run.run_id),
                "raw_id": str(raw.id),
                "raw_key": raw.raw_path,
            }
        )
    return samples


_ADAPTERS = {
    "arxiv": SourceRecoveryAdapter(
        name="arxiv",
        raw_model=ArxivRawResponse,
        entity_table="arxiv_papers",
        match_table="arxiv_topic_matches",
        raw_table="arxiv_raw_responses",
        lineage_sampler=_arxiv_lineage_samples,
    ),
    "github": SourceRecoveryAdapter(
        name="github",
        raw_model=GithubRawResponse,
        entity_table="github_repositories",
        match_table="github_topic_repository_matches",
        raw_table="github_raw_responses",
        snapshot_table="github_repository_snapshots",
        observation_date_column=GithubRepositorySnapshot.observation_date,
        lineage_sampler=_github_lineage_samples,
    ),
}

SOURCE_RECOVERY_ADAPTERS = MappingProxyType(_ADAPTERS)


def recovery_source_names() -> tuple[str, ...]:
    """Return deterministic names for every source in the verified recovery unit."""

    return tuple(sorted(SOURCE_RECOVERY_ADAPTERS))


def recovery_adapter(source: str) -> SourceRecoveryAdapter:
    """Return a source adapter or fail closed for unregistered persisted evidence."""

    try:
        return SOURCE_RECOVERY_ADAPTERS[source]
    except KeyError as error:
        raise ValueError(f"source {source!r} has no recovery adapter") from error
