"""Database models and repositories for Signal Observatory."""

from observatory_db.arxiv_models import (
    ArxivAuthor,
    ArxivCategory,
    ArxivCollectionCursor,
    ArxivPaper,
    ArxivPaperAuthor,
    ArxivPaperCategory,
    ArxivPaperObservation,
    ArxivRawResponse,
    ArxivTopicMatch,
)
from observatory_db.base import Base
from observatory_db.models import (
    DataQualityCheck,
    IngestionError,
    IngestionRun,
    Source,
    Topic,
    TopicAlias,
    TopicCategory,
    TopicRegistryAuditLog,
    TopicRegistryVersion,
    TopicSourceMapping,
)

__all__ = [
    "Base",
    "ArxivAuthor",
    "ArxivCategory",
    "ArxivCollectionCursor",
    "ArxivPaper",
    "ArxivPaperAuthor",
    "ArxivPaperCategory",
    "ArxivPaperObservation",
    "ArxivRawResponse",
    "ArxivTopicMatch",
    "DataQualityCheck",
    "IngestionError",
    "IngestionRun",
    "Source",
    "Topic",
    "TopicAlias",
    "TopicCategory",
    "TopicRegistryAuditLog",
    "TopicRegistryVersion",
    "TopicSourceMapping",
]
