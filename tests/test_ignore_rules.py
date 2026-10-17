"""Nested Git ignore semantics, exclusion from artifacts and bounded traversal."""

import io
import subprocess
import zipfile

import pytest

from api.config import settings
from api.ingestion.sources import SourceError, extract_zip, read_files
from api.worker import run_once
from tests.conftest import register
from tests.test_indexing import archive_bytes


def test_nested_ignores_match_git_and_do_not_read_pruned_rules(tmp_path):
    files = {
        ".gitignore": "*.cache\nexcluded/\n!kept.cache\n",
        "kept.cache": "kept",
        "other.cache": "ignored",
        "main.py": "pass",
        "src/.gitignore": "*.py\n!safe.py\n/local.txt\n",
        "src/safe.py": "pass",
        "src/hidden.py": "pass",
        "src/local.txt": "ignored",
        "src/deep/local.txt": "kept",
        "src/deep/.gitignore": "!allowed.py\n",
        "src/deep/allowed.py": "pass",
        "src/deep/no.py": "pass",
        # Parent directory exclusion wins even over an oversized nested ignore file.
        "excluded/.gitignore": "!anything\n" * 10000,
        "excluded/anything": "ignored",
        "node_modules/dependency.py": "ignored",
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    indexed = read_files(tmp_path)
    for name in files:
        if name.startswith("node_modules/"):
            assert name not in indexed
            continue
        result = subprocess.run(
            ["git", "-C", str(tmp_path), "check-ignore", "--no-index", "--quiet", name]
        )
        assert (name not in indexed) == (result.returncode == 0), name
    assert "src/deep/allowed.py" in indexed and "src/deep/no.py" not in indexed


def test_ignore_rule_budgets_fail_closed(tmp_path):
    (tmp_path / ".gitignore").write_text("a" * 65537)
    with pytest.raises(SourceError, match="ignore rules exceed size"):
        read_files(tmp_path)
    (tmp_path / ".gitignore").write_text("*.cache\n" * 4097)
    with pytest.raises(SourceError, match="too many ignore"):
        read_files(tmp_path)


def test_ignored_and_binary_files_are_absent_from_published_artifact(client, db):
    from api.graph import store
    from api.models import Repository

    register(client)
    payload = archive_bytes(
        {
            ".gitignore": "private/\n",
            "main.py": "def public(): pass\n",
            "private/secret.txt": "test-secret-must-not-be-retained",
            "asset.bin": b"\0binary",
        }
    )
    response = client.post(
        "/api/repositories/upload", files={"file": ("ignore.zip", payload, "application/zip")}
    )
    repo_id = response.json()["repository"]["id"]
    run_once()
    repo = db.get(Repository, repo_id)
    assert repo.status == "ready"
    root = settings().data_dir.resolve() / "snapshots" / repo_id / repo.stats["tree_hash"]
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()) == [
        ".gitignore",
        "main.py",
    ]
    assert client.get(f"/api/repositories/{repo_id}/search?q=secret").json()["results"] == []
    store.delete_graph(repo.graph_name)


def test_archive_count_size_and_duplicate_limits(tmp_path, monkeypatch):
    source = tmp_path / "archive.zip"
    monkeypatch.setattr(settings(), "max_files", 1)
    source.write_bytes(archive_bytes({"one.py": "pass", "two.py": "pass", "three.py": "pass"}))
    with pytest.raises(SourceError, match="too many entries"):
        extract_zip(source, tmp_path / "count")
    monkeypatch.setattr(settings(), "max_files", 10)
    monkeypatch.setattr(settings(), "max_file_bytes", 32)
    source.write_bytes(archive_bytes({"large.py": "x" * 1000}))
    with pytest.raises(SourceError, match="extraction limits"):
        extract_zip(source, tmp_path / "size")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("duplicate.py", "pass")
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("duplicate.py", "other")
    source.write_bytes(buffer.getvalue())
    with pytest.raises(SourceError, match="duplicate file paths"):
        extract_zip(source, tmp_path / "duplicate")


def test_directory_budget_and_symlink_escape(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("must not read")
    (source / "link.txt").symlink_to(outside)
    (source / "directory-link").symlink_to(tmp_path, target_is_directory=True)
    assert read_files(source) == {}
    monkeypatch.setattr(settings(), "max_files", 1)
    for n in range(5):
        (source / str(n)).mkdir()
    with pytest.raises(SourceError, match="directory traversal limit"):
        read_files(source)


def test_repository_python_is_data_and_is_never_executed(client, db, tmp_path):
    from api.graph import store
    from api.models import Repository

    marker = tmp_path / "source-was-executed"
    register(client)
    source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\ndef harmless():\n    return 1\n"
    response = client.post(
        "/api/repositories/upload",
        files={
            "file": ("untrusted.zip", archive_bytes({"untrusted.py": source}), "application/zip")
        },
    )
    assert response.status_code == 201
    repo_id = response.json()["repository"]["id"]
    run_once()
    assert not marker.exists()
    repo = db.get(Repository, repo_id)
    assert repo.status == "ready" and repo.stats["functions"] == 1
    store.delete_graph(repo.graph_name)
