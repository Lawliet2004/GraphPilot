"""Independent repositories may index concurrently on the same graph service."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from redis.exceptions import ResponseError

from api.graph import store
from api.ingestion.python import build_graph, parse_file


def test_copy_retries_are_bounded_and_only_for_known_transient_failure(monkeypatch):
    failures = {"message": "GRAPH.COPY failed, could not fork", "calls": 0}

    def copy(_):
        failures["calls"] += 1
        raise ResponseError(failures["message"])

    monkeypatch.setattr(
        store, "client", lambda: SimpleNamespace(select_graph=lambda _: SimpleNamespace(copy=copy))
    )
    monkeypatch.setattr(store.time, "sleep", lambda _: None)
    with pytest.raises(ResponseError):
        store.copy_snapshot("old", "new")
    assert failures["calls"] == 7
    failures.update(message="An unrelated graph write error", calls=0)
    with pytest.raises(ResponseError):
        store.copy_snapshot("old", "new")
    assert failures["calls"] == 1


def test_concurrent_isolated_graph_snapshot_publication():
    names = []

    def run(number):
        repo_id = str(uuid.uuid4())
        source = "def first():\n    return 1\n\ndef caller():\n    return first()\n"
        files = {
            "service.py": {
                "hash": "fixture",
                "lines": 5,
                "parsed": parse_file("service.py", source),
            }
        }
        nodes, edges, _ = build_graph(repo_id, "main", "a" * 40, "Concurrent fixture", files)
        previous = store.graph_name(repo_id, "main", "original")
        names.append(previous)
        store.create_graph(previous, nodes, edges)
        for index in range(6):
            target = store.graph_name(repo_id, "main", str(index))
            names.append(target)
            old_nodes, old_edges = store.manifest(previous)
            store.update_snapshot(previous, target, old_nodes, old_edges, nodes, edges)
            assert store.query(target, "MATCH (n:Entity) RETURN count(n)")[0][0] == len(nodes)
            previous = target
        return number

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert set(pool.map(run, [1, 2])) == {1, 2}
    finally:
        for name in names:
            store.delete_graph(name)
