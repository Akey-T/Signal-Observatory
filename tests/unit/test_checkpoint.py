from pathlib import Path

from collector_core import LocalCheckpointStore


def test_checkpoint_round_trip_and_replacement(tmp_path: Path) -> None:
    store = LocalCheckpointStore(tmp_path)

    assert store.get("example-api") is None
    store.set("example-api", {"cursor": "first"})
    store.set("example-api", {"cursor": "second"})

    assert store.get("example-api") == {"cursor": "second"}
    assert [path.name for path in tmp_path.iterdir()] == ["example-api.json"]
