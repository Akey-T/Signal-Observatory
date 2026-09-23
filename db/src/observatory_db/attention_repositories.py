"""Idempotent persistence helpers for the source-neutral Attention Domain."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from math import isfinite
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from attention_domain import (
    AttentionDocumentIdentity,
    AttentionDocumentType,
    AttentionEvidenceRole,
    AttentionMetricDefinition,
    AttentionObservationIdentity,
    AttentionObservationState,
)
from observatory_db.attention_models import (
    AttentionDocument,
    AttentionObservation,
    AttentionObservationEvidence,
)
from observatory_db.models import IngestionRun, Source, TopicSourceMapping


class AttentionDocumentRepository:
    """Upsert source-local Documents without creating canonical entities or events."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self,
        *,
        source_id: UUID,
        identity: AttentionDocumentIdentity,
        document_type: AttentionDocumentType,
        observed_at: datetime,
        canonical_url: str | None = None,
        title: str | None = None,
        published_at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[AttentionDocument, bool]:
        observed = _utc(observed_at, "observed_at")
        published = _utc(published_at, "published_at") if published_at else None
        source_name = self._session.scalar(select(Source.name).where(Source.id == source_id))
        if source_name is None:
            raise ValueError("attention document source does not exist")
        if source_name != identity.source_name:
            raise ValueError("attention document identity does not match source")
        row = self._session.scalar(
            select(AttentionDocument).where(
                AttentionDocument.source_id == source_id,
                AttentionDocument.source_document_key == identity.source_document_key,
            )
        )
        if row is None:
            row = AttentionDocument(
                source_id=source_id,
                source_document_key=identity.source_document_key,
                canonical_url=canonical_url,
                title=title,
                published_at=published,
                first_observed_at=observed,
                last_observed_at=observed,
                document_type=document_type,
                metadata_=dict(metadata or {}),
            )
            self._session.add(row)
            self._session.flush()
            return row, True

        previous_last = _utc(row.last_observed_at, "last_observed_at")
        row.first_observed_at = min(_utc(row.first_observed_at, "first_observed_at"), observed)
        row.last_observed_at = max(previous_last, observed)
        if observed >= previous_last:
            if canonical_url is not None:
                row.canonical_url = canonical_url
            if title is not None:
                row.title = title
            if published is not None:
                row.published_at = published
            row.document_type = document_type
            row.metadata_ = {**row.metadata_, **dict(metadata or {})}
        self._session.flush()
        return row, False


class AttentionObservationRepository:
    """Persist logical interval measurements and sampled Evidence links idempotently."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self,
        *,
        identity: AttentionObservationIdentity,
        metric: AttentionMetricDefinition,
        numeric_value: float | None,
        collection_state: AttentionObservationState,
        observed_at: datetime,
        ingestion_run_id: UUID | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[AttentionObservation, bool]:
        if identity.metric_name != metric.name:
            raise ValueError(
                f"observation identity metric {identity.metric_name!r} does not match "
                f"definition {metric.name!r}"
            )
        if identity.channel is not metric.channel:
            raise ValueError("observation identity channel does not match metric definition")
        if numeric_value is not None and not isfinite(numeric_value):
            raise ValueError("attention observation numeric value must be finite")
        mapping = self._session.get(TopicSourceMapping, identity.source_mapping_id)
        if mapping is None:
            raise ValueError("attention observation source mapping does not exist")
        if mapping.topic_id != identity.topic_id or mapping.source_id != identity.source_id:
            raise ValueError("attention observation identity does not match source mapping")
        if ingestion_run_id is not None:
            ingestion_run = self._session.get(IngestionRun, ingestion_run_id)
            if ingestion_run is None:
                raise ValueError("attention observation ingestion run does not exist")
            if ingestion_run.source_id != identity.source_id:
                raise ValueError("attention observation ingestion run does not match source")
        observed = _utc(observed_at, "observed_at")
        row = self._session.scalar(
            select(AttentionObservation).where(
                AttentionObservation.topic_id == identity.topic_id,
                AttentionObservation.source_id == identity.source_id,
                AttentionObservation.source_mapping_id == identity.source_mapping_id,
                AttentionObservation.channel == identity.channel,
                AttentionObservation.metric_name == metric.name,
                AttentionObservation.window_start == identity.window_start,
                AttentionObservation.window_end == identity.window_end,
            )
        )
        if row is None:
            row = AttentionObservation(
                topic_id=identity.topic_id,
                source_id=identity.source_id,
                source_mapping_id=identity.source_mapping_id,
                channel=identity.channel,
                window_start=identity.window_start,
                window_end=identity.window_end,
                metric_name=metric.name,
                numeric_value=numeric_value,
                unit=metric.unit,
                definition_version=metric.definition_version,
                collection_state=collection_state,
                ingestion_run_id=ingestion_run_id,
                first_observed_at=observed,
                last_observed_at=observed,
                metadata_=dict(metadata or {}),
            )
            self._session.add(row)
            self._session.flush()
            return row, True

        previous_last = _utc(row.last_observed_at, "last_observed_at")
        row.first_observed_at = min(_utc(row.first_observed_at, "first_observed_at"), observed)
        row.last_observed_at = max(previous_last, observed)
        if observed >= previous_last:
            row.numeric_value = numeric_value
            row.unit = metric.unit
            row.definition_version = metric.definition_version
            row.collection_state = collection_state
            if ingestion_run_id is not None:
                row.ingestion_run_id = ingestion_run_id
            row.metadata_ = {**row.metadata_, **dict(metadata or {})}
        self._session.flush()
        return row, False

    def link_evidence(
        self,
        *,
        observation_id: UUID,
        document_id: UUID,
        evidence_role: AttentionEvidenceRole,
        rank: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[AttentionObservationEvidence, bool]:
        if rank is not None and rank < 0:
            raise ValueError("evidence rank cannot be negative")
        observation = self._session.get(AttentionObservation, observation_id)
        document = self._session.get(AttentionDocument, document_id)
        if observation is None or document is None:
            raise ValueError("attention evidence observation and document must exist")
        if observation.source_id != document.source_id:
            raise ValueError("attention evidence document must belong to the observation source")
        row = self._session.scalar(
            select(AttentionObservationEvidence).where(
                AttentionObservationEvidence.observation_id == observation_id,
                AttentionObservationEvidence.document_id == document_id,
                AttentionObservationEvidence.evidence_role == evidence_role,
            )
        )
        if row is None:
            row = AttentionObservationEvidence(
                observation_id=observation_id,
                document_id=document_id,
                evidence_role=evidence_role,
                rank=rank,
                metadata_=dict(metadata or {}),
            )
            self._session.add(row)
            self._session.flush()
            return row, True
        row.rank = rank
        row.metadata_ = {**row.metadata_, **dict(metadata or {})}
        self._session.flush()
        return row, False


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)
