"""Strict-enough JSON parsing for public GitHub Repository metadata."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from github_collector.models import GithubRepositoryData, GithubSearchResult


class GithubParseError(ValueError):
    """Raised when a GitHub payload cannot produce trustworthy Repository metadata."""


class GithubJsonParser:
    def parse_search(self, payload: bytes) -> GithubSearchResult:
        value = self._json(payload)
        if not isinstance(value, dict) or not isinstance(value.get("items"), list):
            raise GithubParseError("GitHub search payload must contain an items array")
        try:
            repositories = tuple(self._repository(item) for item in value["items"])
            return GithubSearchResult(
                total_count=int(value["total_count"]),
                incomplete_results=bool(value.get("incomplete_results", False)),
                repositories=repositories,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise GithubParseError(f"invalid GitHub search payload: {error}") from error

    def parse_repository(self, payload: bytes) -> GithubRepositoryData:
        value = self._json(payload)
        if not isinstance(value, dict):
            raise GithubParseError("GitHub repository payload must be an object")
        try:
            return self._repository(value)
        except (KeyError, TypeError, ValueError) as error:
            raise GithubParseError(f"invalid GitHub repository payload: {error}") from error

    def _repository(self, value: object) -> GithubRepositoryData:
        if not isinstance(value, dict):
            raise GithubParseError("repository item must be an object")
        owner = value.get("owner")
        if not isinstance(owner, dict):
            raise GithubParseError("repository owner must be an object")
        parent = value.get("parent")
        license_value = value.get("license")
        topics = value.get("topics", [])
        if not isinstance(topics, list):
            raise GithubParseError("repository topics must be an array")
        parent_id = parent.get("id") if isinstance(parent, dict) else None
        license_spdx = license_value.get("spdx_id") if isinstance(license_value, dict) else None
        return GithubRepositoryData(
            github_repository_id=int(value["id"]),
            node_id=str(value["node_id"]),
            owner_login=str(owner["login"]),
            name=str(value["name"]),
            full_name=str(value["full_name"]),
            html_url=str(value["html_url"]),
            api_url=str(value["url"]),
            description=self._optional_string(value.get("description")),
            homepage=self._optional_string(value.get("homepage")),
            language=self._optional_string(value.get("language")),
            default_branch=self._optional_string(value.get("default_branch")),
            is_fork=bool(value.get("fork", False)),
            fork_parent_github_id=self._optional_int(parent_id),
            archived=bool(value.get("archived", False)),
            disabled=bool(value.get("disabled", False)),
            visibility=str(value.get("visibility", "public")),
            created_at_github=self._datetime(value["created_at"]),
            updated_at_github=self._datetime(value["updated_at"]),
            pushed_at_github=self._optional_datetime(value.get("pushed_at")),
            stargazers_count=self._count(value.get("stargazers_count")),
            forks_count=self._count(value.get("forks_count", value.get("forks"))),
            open_issues_count=self._count(value.get("open_issues_count")),
            subscribers_count=self._count(value.get("subscribers_count")),
            size_kb=self._count(value.get("size")),
            topics=tuple(str(topic) for topic in topics),
            license_spdx=self._optional_string(license_spdx),
            metadata={
                "private": bool(value.get("private", False)),
                "has_issues": bool(value.get("has_issues", False)),
                "has_wiki": bool(value.get("has_wiki", False)),
            },
        )

    @staticmethod
    def _json(payload: bytes) -> object:
        try:
            return json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GithubParseError("GitHub response is not valid UTF-8 JSON") from error

    @staticmethod
    def _datetime(value: object) -> datetime:
        if not isinstance(value, str):
            raise GithubParseError("required GitHub timestamp is missing")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise GithubParseError("GitHub timestamp must include a timezone")
        return parsed.astimezone(UTC)

    def _optional_datetime(self, value: object) -> datetime | None:
        return None if value is None else self._datetime(value)

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _optional_int(value: object) -> int | None:
        return None if value is None else int(str(value))

    @staticmethod
    def _count(value: object) -> int:
        return 0 if value is None else int(str(value))
