"""Structured ingestion lifecycle logging."""

from __future__ import annotations

import structlog

from collector_core.models import CollectorContext, CollectorResult


class StructlogRunLogger:
    def __init__(self) -> None:
        self._logger = structlog.get_logger("collector")

    def started(self, context: CollectorContext) -> None:
        self._logger.info("ingestion_started", run_id=str(context.run_id), source=context.source)

    def completed(self, context: CollectorContext, result: CollectorResult) -> None:
        self._logger.info(
            "ingestion_completed",
            run_id=str(context.run_id),
            source=context.source,
            **result.model_dump(exclude={"checkpoint_after", "metadata"}),
        )

    def failed(self, context: CollectorContext, error: BaseException) -> None:
        self._logger.exception(
            "ingestion_failed",
            run_id=str(context.run_id),
            source=context.source,
            error_type=type(error).__name__,
        )
