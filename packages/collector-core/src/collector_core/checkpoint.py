"""Small atomic file-backed checkpoint store."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SOURCE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class LocalCheckpointStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def get(self, source: str) -> dict[str, Any] | None:
        path = self._path(source)
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as checkpoint_file:
            return dict(json.load(checkpoint_file))

    def set(self, source: str, checkpoint: Mapping[str, Any]) -> None:
        path = self._path(source)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{source}-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as temporary_file:
                json.dump(dict(checkpoint), temporary_file, sort_keys=True, separators=(",", ":"))
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_name, path)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise

    def _path(self, source: str) -> Path:
        if SOURCE_PATTERN.fullmatch(source) is None:
            raise ValueError("invalid source name")
        return self.root / f"{source}.json"
