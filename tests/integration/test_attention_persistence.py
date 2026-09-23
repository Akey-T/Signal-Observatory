from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from attention_domain import (
    AttentionChannel,
    AttentionDocumentIdentity,
    AttentionDocumentType,
    AttentionEvidenceRole,
    AttentionMetricDefinition,
    AttentionObservationIdentity,
    AttentionObservationState,
)
from observatory_db import (
    AttentionDocument,
    AttentionDocumentRepository,
    AttentionObservation,
    AttentionObservationEvidence,
    AttentionObservationRepository,
    IngestionRun,
    Source,
    Topic,
    TopicSourceMapping,
)
from observatory_db.models import IngestionStatus


def test_attention_minimal_persistence_is_idempotent_and_many_to_many(
    migrated_engine: Engine,
) -> None:
    observed = datetime(2026, 9, 7, 10, tzinfo=UTC)
    with Session(migrated_engine) as session:
        source = Source(name="synthetic_attention", kind="fixture", metadata_={})
        topic_one = Topic(
            canonical_name="Housing Affordability",
            normalized_name="housing affordability",
            slug="housing-affordability",
        )
        topic_two = Topic(
            canonical_name="Inflation",
            normalized_name="inflation",
            slug="inflation",
        )
        session.add_all([source, topic_one, topic_two])
        session.flush()
        mapping_one = TopicSourceMapping(
            topic_id=topic_one.id,
            source_id=source.id,
            enabled=True,
            mapping_type="fixture",
            query="housing affordability",
            configuration={},
        )
        mapping_two = TopicSourceMapping(
            topic_id=topic_two.id,
            source_id=source.id,
            enabled=True,
            mapping_type="fixture",
            query="inflation",
            configuration={},
        )
        session.add_all([mapping_one, mapping_two])
        session.flush()
        run = IngestionRun(
            source_id=source.id,
            started_at=observed,
            finished_at=observed,
            status=IngestionStatus.SUCCEEDED,
            collector_version="fixture-v1",
            metadata_={"external_requests": 0},
        )
        session.add(run)
        session.flush()

        documents = AttentionDocumentRepository(session)
        document, document_created = documents.upsert(
            source_id=source.id,
            identity=AttentionDocumentIdentity("synthetic_attention", "doc-1"),
            document_type=AttentionDocumentType.ARTICLE,
            observed_at=observed,
            canonical_url="https://example.test/article/1",
            title="Housing costs and inflation",
            metadata={"fixture": True},
        )
        same_document, same_document_created = documents.upsert(
            source_id=source.id,
            identity=AttentionDocumentIdentity("synthetic_attention", "doc-1"),
            document_type=AttentionDocumentType.ARTICLE,
            observed_at=observed + timedelta(minutes=5),
            title="Housing costs and inflation (updated)",
        )
        stale_document, stale_document_created = documents.upsert(
            source_id=source.id,
            identity=AttentionDocumentIdentity("synthetic_attention", "doc-1"),
            document_type=AttentionDocumentType.ARTICLE,
            observed_at=observed - timedelta(hours=1),
            title="stale title",
            metadata={"stale": True},
        )
        assert document_created
        assert not same_document_created
        assert not stale_document_created
        assert same_document.id == document.id
        assert stale_document.title == "Housing costs and inflation (updated)"
        assert stale_document.first_observed_at == observed - timedelta(hours=1)
        assert stale_document.last_observed_at == observed + timedelta(minutes=5)
        assert "stale" not in stale_document.metadata_

        metric = AttentionMetricDefinition(
            name="MEDIA_MATCH_COUNT",
            channel=AttentionChannel.MEDIA,
            unit="articles",
            description="Synthetic measured media matches.",
            definition_version="fixture-v1",
        )
        observations = AttentionObservationRepository(session)
        observation_one, first_created = observations.upsert(
            identity=AttentionObservationIdentity(
                topic_id=topic_one.id,
                source_id=source.id,
                source_mapping_id=mapping_one.id,
                channel=AttentionChannel.MEDIA,
                metric_name=metric.name,
                window_start=observed,
                window_end=observed + timedelta(hours=1),
            ),
            metric=metric,
            numeric_value=0,
            collection_state=AttentionObservationState.VALID,
            observed_at=observed,
            ingestion_run_id=run.run_id,
        )
        same_observation, second_created = observations.upsert(
            identity=AttentionObservationIdentity(
                topic_id=topic_one.id,
                source_id=source.id,
                source_mapping_id=mapping_one.id,
                channel=AttentionChannel.MEDIA,
                metric_name=metric.name,
                window_start=observed,
                window_end=observed + timedelta(hours=1),
            ),
            metric=metric,
            numeric_value=0,
            collection_state=AttentionObservationState.VALID,
            observed_at=observed + timedelta(minutes=10),
            ingestion_run_id=run.run_id,
        )
        stale_observation, stale_observation_created = observations.upsert(
            identity=AttentionObservationIdentity(
                topic_id=topic_one.id,
                source_id=source.id,
                source_mapping_id=mapping_one.id,
                channel=AttentionChannel.MEDIA,
                metric_name=metric.name,
                window_start=observed,
                window_end=observed + timedelta(hours=1),
            ),
            metric=metric,
            numeric_value=99,
            collection_state=AttentionObservationState.PARTIAL,
            observed_at=observed - timedelta(hours=1),
            ingestion_run_id=run.run_id,
            metadata={"stale": True},
        )
        observation_two, _ = observations.upsert(
            identity=AttentionObservationIdentity(
                topic_id=topic_two.id,
                source_id=source.id,
                source_mapping_id=mapping_two.id,
                channel=AttentionChannel.MEDIA,
                metric_name=metric.name,
                window_start=observed,
                window_end=observed + timedelta(hours=1),
            ),
            metric=metric,
            numeric_value=5,
            collection_state=AttentionObservationState.PARTIAL,
            observed_at=observed,
            ingestion_run_id=run.run_id,
        )
        assert first_created
        assert not second_created
        assert not stale_observation_created
        assert same_observation.id == observation_one.id
        assert stale_observation.numeric_value == 0
        assert stale_observation.collection_state is AttentionObservationState.VALID
        assert stale_observation.first_observed_at == observed - timedelta(hours=1)
        assert stale_observation.last_observed_at == observed + timedelta(minutes=10)
        assert "stale" not in stale_observation.metadata_
        assert observation_one.numeric_value == 0
        assert observation_two.numeric_value == 5

        first_link, first_link_created = observations.link_evidence(
            observation_id=observation_one.id,
            document_id=document.id,
            evidence_role=AttentionEvidenceRole.SAMPLE,
            rank=1,
        )
        same_link, same_link_created = observations.link_evidence(
            observation_id=observation_one.id,
            document_id=document.id,
            evidence_role=AttentionEvidenceRole.SAMPLE,
            rank=1,
        )
        second_topic_link, _ = observations.link_evidence(
            observation_id=observation_two.id,
            document_id=document.id,
            evidence_role=AttentionEvidenceRole.EXAMPLE,
        )
        session.commit()

        assert first_link_created
        assert not same_link_created
        assert first_link.id == same_link.id
        assert second_topic_link.document_id == document.id
        assert session.scalar(select(AttentionDocument).where(AttentionDocument.id == document.id))
        assert len(session.scalars(select(AttentionObservation)).all()) == 2
        assert len(session.scalars(select(AttentionObservationEvidence)).all()) == 2
        assert observation_one.ingestion_run_id == run.run_id
        assert observation_one.numeric_value == 0

    tables = set(inspect(migrated_engine).get_table_names())
    assert "attention_entities" not in tables
    assert "attention_events" not in tables


def test_attention_persistence_rejects_cross_source_lineage(
    migrated_engine: Engine,
) -> None:
    observed = datetime(2026, 9, 7, 10, tzinfo=UTC)
    with Session(migrated_engine) as session:
        source = Source(name="attention_one", kind="fixture", metadata_={})
        other_source = Source(name="attention_two", kind="fixture", metadata_={})
        topic = Topic(
            canonical_name="Housing Affordability",
            normalized_name="housing affordability",
            slug="housing-affordability-lineage",
        )
        session.add_all([source, other_source, topic])
        session.flush()
        mapping = TopicSourceMapping(
            topic_id=topic.id,
            source_id=source.id,
            enabled=True,
            mapping_type="fixture",
            query="housing affordability",
            configuration={},
        )
        other_run = IngestionRun(
            source_id=other_source.id,
            started_at=observed,
            finished_at=observed,
            status=IngestionStatus.SUCCEEDED,
            collector_version="fixture-v1",
            metadata_={},
        )
        session.add_all([mapping, other_run])
        session.flush()

        documents = AttentionDocumentRepository(session)
        with pytest.raises(ValueError, match="identity does not match source"):
            documents.upsert(
                source_id=source.id,
                identity=AttentionDocumentIdentity("attention_two", "doc-mismatch"),
                document_type=AttentionDocumentType.ARTICLE,
                observed_at=observed,
            )

        metric = AttentionMetricDefinition(
            name="MEDIA_MATCH_COUNT",
            channel=AttentionChannel.MEDIA,
            unit="articles",
            description="Synthetic measured media matches.",
            definition_version="fixture-v1",
        )
        observations = AttentionObservationRepository(session)
        identity = AttentionObservationIdentity(
            topic_id=topic.id,
            source_id=source.id,
            source_mapping_id=mapping.id,
            channel=AttentionChannel.MEDIA,
            metric_name=metric.name,
            window_start=observed,
            window_end=observed + timedelta(hours=1),
        )
        with pytest.raises(ValueError, match="ingestion run does not match source"):
            observations.upsert(
                identity=identity,
                metric=metric,
                numeric_value=1,
                collection_state=AttentionObservationState.VALID,
                observed_at=observed,
                ingestion_run_id=other_run.run_id,
            )
        mismatched_identity = AttentionObservationIdentity(
            topic_id=topic.id,
            source_id=other_source.id,
            source_mapping_id=mapping.id,
            channel=AttentionChannel.MEDIA,
            metric_name=metric.name,
            window_start=observed,
            window_end=observed + timedelta(hours=1),
        )
        with pytest.raises(ValueError, match="identity does not match source mapping"):
            observations.upsert(
                identity=mismatched_identity,
                metric=metric,
                numeric_value=1,
                collection_state=AttentionObservationState.VALID,
                observed_at=observed,
            )
        with pytest.raises(ValueError, match="numeric value must be finite"):
            observations.upsert(
                identity=identity,
                metric=metric,
                numeric_value=float("nan"),
                collection_state=AttentionObservationState.VALID,
                observed_at=observed,
            )

        observation, _ = observations.upsert(
            identity=identity,
            metric=metric,
            numeric_value=1,
            collection_state=AttentionObservationState.VALID,
            observed_at=observed,
        )
        other_document, _ = documents.upsert(
            source_id=other_source.id,
            identity=AttentionDocumentIdentity("attention_two", "doc-other"),
            document_type=AttentionDocumentType.ARTICLE,
            observed_at=observed,
        )
        with pytest.raises(ValueError, match="must belong to the observation source"):
            observations.link_evidence(
                observation_id=observation.id,
                document_id=other_document.id,
                evidence_role=AttentionEvidenceRole.SAMPLE,
            )
