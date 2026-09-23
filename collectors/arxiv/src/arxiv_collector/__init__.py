"""Official-API-only arXiv Research Collector."""

from arxiv_collector.audit import ArxivCursorAuditor
from arxiv_collector.client import (
    ArxivClient,
    ArxivClientError,
    ArxivForbiddenError,
    ArxivHTTPError,
    ArxivTransportError,
    MinimumIntervalLimiter,
)
from arxiv_collector.models import (
    ArxivHTTPResponse,
    ArxivRequest,
    ParsedArxivArticle,
    ParsedArxivFeed,
)
from arxiv_collector.parser import ArxivAPIError, ArxivAtomParser, ArxivParseError
from arxiv_collector.persistence import ArxivPersistence, normalize_author_name
from arxiv_collector.queries import ArxivQueryService
from arxiv_collector.query import ArxivQueryBuilder, ArxivQueryError
from arxiv_collector.service import (
    ArxivCollectionError,
    ArxivCollectionService,
    ArxivRunSummary,
    QueryWindow,
)

__all__ = [
    "ArxivAPIError",
    "ArxivAtomParser",
    "ArxivClient",
    "ArxivClientError",
    "ArxivCursorAuditor",
    "ArxivCollectionError",
    "ArxivCollectionService",
    "ArxivForbiddenError",
    "ArxivHTTPError",
    "ArxivHTTPResponse",
    "ArxivParseError",
    "ArxivPersistence",
    "ArxivQueryBuilder",
    "ArxivQueryError",
    "ArxivQueryService",
    "ArxivRequest",
    "ArxivRunSummary",
    "ArxivTransportError",
    "MinimumIntervalLimiter",
    "ParsedArxivArticle",
    "ParsedArxivFeed",
    "QueryWindow",
    "normalize_author_name",
]
