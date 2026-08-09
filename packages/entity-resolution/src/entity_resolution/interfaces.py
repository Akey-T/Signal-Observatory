"""Minimal future boundary for explicit, auditable alias resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AliasCandidate:
    source: str
    alias: str


class EntityResolver(Protocol):
    def resolve(self, candidate: AliasCandidate) -> UUID | None: ...
