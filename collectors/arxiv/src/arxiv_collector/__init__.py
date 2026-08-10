"""Official-API-only arXiv Research Collector."""

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
from arxiv_collector.query import ArxivQueryBuilder, ArxivQueryError

__all__ = [
    "ArxivAPIError",
    "ArxivAtomParser",
    "ArxivClient",
    "ArxivClientError",
    "ArxivForbiddenError",
    "ArxivHTTPError",
    "ArxivHTTPResponse",
    "ArxivParseError",
    "ArxivPersistence",
    "ArxivQueryBuilder",
    "ArxivQueryError",
    "ArxivRequest",
    "ArxivTransportError",
    "MinimumIntervalLimiter",
    "ParsedArxivArticle",
    "ParsedArxivFeed",
    "normalize_author_name",
]
