"""Contracts for future reproducible Gold datasets."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GoldMetric:
    topic_id: UUID
    metric_name: str
    window_start: datetime
    window_end: datetime
    value: float
    definition_version: str

    def __post_init__(self) -> None:
        for attribute in ("window_start", "window_end"):
            value = getattr(self, attribute)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{attribute} must be timezone-aware")
            object.__setattr__(self, attribute, value.astimezone(UTC))
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        if not self.definition_version:
            raise ValueError("definition_version is required")


class GoldMetricReader(Protocol):
    def read(
        self,
        *,
        topic_id: UUID,
        metric_name: str,
        window_start: datetime,
        window_end: datetime,
    ) -> Sequence[GoldMetric]: ...
