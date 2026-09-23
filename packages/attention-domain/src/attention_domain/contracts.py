"""Source-neutral contracts for attention measurements and evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID


class AttentionChannel(StrEnum):
    """What kind of attention signal a source measures."""

    MEDIA = "media"
    SEARCH = "search"
    COMMUNITY = "community"
    REFERENCE = "reference"


class AttentionDocumentType(StrEnum):
    ARTICLE = "article"
    POST = "post"
    STORY = "story"
    REFERENCE_PAGE = "reference_page"
    OTHER = "other"


class AttentionObservationState(StrEnum):
    VALID = "valid"
    PARTIAL = "partial"


class AttentionEvidenceRole(StrEnum):
    SAMPLE = "sample"
    MATCH = "match"
    EXAMPLE = "example"
    SOURCE_RECORD = "source_record"


class EntityType(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    COMPANY = "company"
    LOCATION = "location"
    PRODUCT = "product"
    OTHER = "other"


class EntityStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class EventStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"
    MERGED = "merged"
    DEPRECATED = "deprecated"


class EventCreationMethod(StrEnum):
    CURATED = "curated"
    SYSTEM_CANDIDATE = "system_candidate"


_FORBIDDEN_ANALYTICAL_METRICS = {
    "TREND_SCORE",
    "MOMENTUM",
    "ACCELERATION",
    "BREAKOUT_SCORE",
    "PUBLIC_ATTENTION_SCORE",
    "PUBLIC_CONCERN_SCORE",
}


def _normalize_metric_name(value: str) -> str:
    return "_".join(_require_text(value, "metric name").replace("-", " ").split()).upper()


def _require_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} cannot be empty")
    return normalized


def _require_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware UTC")
    normalized = value.astimezone(UTC)
    return normalized


def _normalize_window(
    window: tuple[datetime, datetime],
    field: str,
) -> tuple[datetime, datetime]:
    if len(window) != 2:
        raise ValueError(f"{field} must contain start and end")
    start = _require_utc(window[0], f"{field}.start")
    end = _require_utc(window[1], f"{field}.end")
    if end <= start:
        raise ValueError(f"{field} end must be after start")
    return start, end


@dataclass(frozen=True, slots=True)
class AttentionMetricDefinition:
    """A measured source metric with explicit unit and definition version."""

    name: str
    channel: AttentionChannel
    unit: str
    description: str
    definition_version: str

    def __post_init__(self) -> None:
        name = _normalize_metric_name(self.name)
        if name in _FORBIDDEN_ANALYTICAL_METRICS:
            raise ValueError(f"analytical metric {name} is outside E05")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "unit", _require_text(self.unit, "metric unit"))
        object.__setattr__(self, "description", _require_text(self.description, "description"))
        object.__setattr__(
            self,
            "definition_version",
            _require_text(self.definition_version, "definition version"),
        )

    def validate_unit(self, unit: str) -> None:
        if unit.strip() != self.unit:
            raise ValueError(f"metric {self.name} requires unit {self.unit!r}")


@dataclass(frozen=True, slots=True)
class AttentionDocumentIdentity:
    """A source-local identity; global entity resolution is intentionally out of scope."""

    source_name: str
    source_document_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_name", _require_text(self.source_name, "source name"))
        object.__setattr__(
            self,
            "source_document_key",
            _require_text(self.source_document_key, "source document key"),
        )


@dataclass(frozen=True, slots=True)
class AttentionObservationIdentity:
    """Logical identity for one Topic/source/channel/metric/time-window measurement."""

    topic_id: UUID
    source_id: UUID
    source_mapping_id: UUID
    channel: AttentionChannel
    metric_name: str
    window_start: datetime
    window_end: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "metric_name",
            _normalize_metric_name(self.metric_name),
        )
        start = _require_utc(self.window_start, "window_start")
        end = _require_utc(self.window_end, "window_end")
        if end <= start:
            raise ValueError("window_end must be after window_start")
        object.__setattr__(self, "window_start", start)
        object.__setattr__(self, "window_end", end)


@dataclass(frozen=True, slots=True)
class AttentionCoverageContract:
    """Coverage semantics an adapter must expose to the existing CoverageDeriver."""

    # Callers should pass the repository's existing CoverageStrategy enum.  The contract keeps
    # this dependency structural so importing the domain package cannot create a db/domain cycle.
    strategy: Any
    expected_window_seconds: int | None = None
    supports_bounded_history: bool = False
    observed_windows: tuple[tuple[datetime, datetime], ...] = ()
    missing_windows: tuple[tuple[datetime, datetime], ...] = ()
    partial_windows: tuple[tuple[datetime, datetime], ...] = ()

    def __post_init__(self) -> None:
        if self.expected_window_seconds is not None and self.expected_window_seconds <= 0:
            raise ValueError("expected window seconds must be positive")
        strategy_value = getattr(self.strategy, "value", self.strategy)
        if strategy_value not in {
            "historical_backfill",
            "forward_snapshot",
            "event_stream",
            "unknown",
            "forward_only",
            "bounded_historical",
            "historical_plus_forward",
        }:
            raise ValueError(f"unsupported coverage strategy {strategy_value!r}")
        if strategy_value == "historical_plus_forward":
            if not self.supports_bounded_history:
                raise ValueError("historical-plus-forward coverage must declare bounded history")
        for field in ("observed_windows", "missing_windows", "partial_windows"):
            windows = tuple(
                _normalize_window(window, f"{field}[{index}]")
                for index, window in enumerate(getattr(self, field))
            )
            object.__setattr__(self, field, windows)


class AttentionSourceAdapter(Protocol):
    """Contract implemented by a future source adapter, without network behavior."""

    @property
    def source_name(self) -> str: ...

    @property
    def channel(self) -> AttentionChannel: ...

    @property
    def coverage(self) -> AttentionCoverageContract: ...

    @property
    def metric_definitions(self) -> tuple[AttentionMetricDefinition, ...]: ...

    @property
    def evidence_semantics(self) -> tuple[AttentionEvidenceRole, ...]: ...

    def document_identity(self, record: Mapping[str, Any]) -> AttentionDocumentIdentity: ...


@dataclass(frozen=True, slots=True)
class CanonicalEntity:
    """Curated canonical entity; collectors cannot instantiate this from observed text."""

    entity_type: EntityType
    canonical_name: str
    normalized_name: str
    description: str | None = None
    status: EntityStatus = EntityStatus.ACTIVE

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "canonical_name",
            _require_text(self.canonical_name, "canonical name"),
        )
        object.__setattr__(
            self,
            "normalized_name",
            _require_text(self.normalized_name, "normalized name").casefold(),
        )
        if self.description is not None:
            object.__setattr__(self, "description", self.description.strip() or None)


@dataclass(frozen=True, slots=True)
class CanonicalEvent:
    """Curated event contract; automatic event creation is deliberately rejected."""

    canonical_title: str
    event_type: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    status: EventStatus = EventStatus.ACTIVE
    creation_method: EventCreationMethod = EventCreationMethod.CURATED

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "canonical_title",
            _require_text(self.canonical_title, "event title"),
        )
        if self.creation_method is not EventCreationMethod.CURATED:
            raise ValueError("system candidates require review before canonical Event creation")
        started = _require_utc(self.started_at, "started_at") if self.started_at else None
        ended = _require_utc(self.ended_at, "ended_at") if self.ended_at else None
        if started and ended and ended < started:
            raise ValueError("ended_at cannot precede started_at")
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "ended_at", ended)


@dataclass(frozen=True, slots=True)
class EventCandidate:
    """Non-canonical future detection output; no persistence or promotion is provided here."""

    candidate_key: str
    window_start: datetime
    window_end: datetime
    representative_title: str
    supporting_document_ids: tuple[UUID, ...]
    source_name: str
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_key",
            _require_text(self.candidate_key, "candidate key"),
        )
        object.__setattr__(
            self,
            "representative_title",
            _require_text(self.representative_title, "title"),
        )
        object.__setattr__(self, "source_name", _require_text(self.source_name, "source name"))
        start = _require_utc(self.window_start, "window_start")
        end = _require_utc(self.window_end, "window_end")
        if end <= start:
            raise ValueError("candidate window_end must be after window_start")
        object.__setattr__(self, "window_start", start)
        object.__setattr__(self, "window_end", end)
        object.__setattr__(self, "created_at", _require_utc(self.created_at, "created_at"))
