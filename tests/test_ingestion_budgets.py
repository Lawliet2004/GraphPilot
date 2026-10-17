import asyncio
import tempfile

import httpx
import pytest
import starlette.formparsers

from api.config import settings
from api.graph import store
from api.ingestion.python import build_graph, parse_file
from api.ingestion.sources import SourceError
from api.main import app
from tests.conftest import register


def test_header_and_chunked_request_limits(client, monkeypatch):
    response = client.post(
        "/api/auth/register", content=b"x" * 65537, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413 and response.headers["x-content-type-options"] == "nosniff"
    response = client.post(
        "/api/auth/register",
        content=iter([b"x" * 32768] * 3),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    monkeypatch.setattr(settings(), "max_archive_bytes", 1000)
    opened = []
    original = tempfile.SpooledTemporaryFile

    def spool(*args, **kwargs):
        file = original(*args, **kwargs)
        opened.append(file)
        return file

    monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", spool)
    register(client)
    response = client.post(
        "/api/repositories/upload", files={"file": ("large.zip", b"x" * 70000, "application/zip")}
    )
    assert response.status_code == 413 and opened == []
    boundary = "budget-fixture"
    start = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="large.zip"\r\nContent-Type: application/zip\r\n\r\n'
    ).encode()

    async def streamed_upload():
        async def chunks():
            for chunk in [
                start,
                b"x" * 32768,
                b"x" * 32768,
                b"x" * 32768,
                f"\r\n--{boundary}--\r\n".encode(),
            ]:
                yield chunk

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app),
            base_url="http://testserver",
            cookies=client.cookies,
            headers={"Origin": "http://testserver", "X-CSRF-Token": client.headers["X-CSRF-Token"]},
        ) as streamed:
            return await streamed.post(
                "/api/repositories/upload",
                content=chunks(),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )

    response = asyncio.run(streamed_upload())
    assert response.status_code == 413
    assert opened and all(file.closed for file in opened)


def test_python_analysis_caps_fail_without_partial_publication():
    with pytest.raises(SourceError, match="AST nodes"):
        parse_file("huge.py", "values=[" + ",".join(["0"] * 50001) + "]")
    with pytest.raises(SourceError, match="2,000 declarations"):
        parse_file("huge.py", "\n".join(f"def function_{i}(): pass" for i in range(2001)))


def test_graph_capacity_is_checked_before_any_database_write(monkeypatch):
    def forbidden():
        raise AssertionError("Oversized graph attempted a database operation")

    monkeypatch.setattr(store, "client", forbidden)
    with pytest.raises(SourceError, match="capacity"):
        store.create_graph("never-created", [{}] * 50001, [])
    with pytest.raises(SourceError, match="capacity"):
        store.update_snapshot("old", "never-created", [], [], [], [{}] * 200001)


def test_ambiguous_module_imports_are_unresolved_and_many_tests_link_correctly():
    files = {}
    for path, source in {
        "a.py": "def same(): pass\n",
        "src/a.py": "def same(): pass\n",
        "caller.py": "import a\ndef run(): return a.same()\n",
    }.items():
        files[path] = {
            "hash": "fixture",
            "lines": len(source.splitlines()),
            "parsed": parse_file(path, source),
        }
    _, edges, stats = build_graph("repo", "main", "commit", "Ambiguity fixture", files)
    assert not any(e["type"] == "CALLS" for e in edges)
    assert stats["unresolved_calls"] == 1 and any(
        "Ambiguous Python module a" in e["message"] for e in stats["parse_errors"]
    )
    source = "def helper(): return 1\n" + "\n".join(
        f"def test_case_{i}(): return helper()" for i in range(1000)
    )
    _, edges, stats = build_graph(
        "repo",
        "main",
        "commit",
        "Larger static fixture",
        {"tests.py": {"hash": "fixture", "lines": 1001, "parsed": parse_file("tests.py", source)}},
    )
    assert stats["resolved_calls"] == 1000 and sum(e["type"] == "TESTS" for e in edges) == 1000
