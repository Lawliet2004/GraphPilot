import subprocess

from api.config import settings
from api.ingestion import sources
from tests.conftest import register

GITHUB = "https://github.com/octocat/Hello-World"


def test_local_repository_defaults_to_its_checked_out_branch(client, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "trunk", str(source)], check=True)
    (source / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "init",
        ],
        check=True,
    )
    settings().allowed_local_roots = [tmp_path]
    register(client)
    created = client.post("/api/repositories", json={"source_type": "local", "source": str(source)})
    assert created.status_code == 201, created.text
    assert created.json()["repository"]["branch"] == "trunk"
    explicit = client.post(
        "/api/repositories",
        json={"source_type": "local", "source": str(source), "branch": "other"},
    )
    assert explicit.json()["repository"]["branch"] == "other"


def test_github_repository_uses_remote_head_when_branch_is_omitted(client, monkeypatch):
    calls = []

    def fake_git(path, *args, **kwargs):
        calls.append(args)
        return "ref: refs/heads/develop\tHEAD\n" + "a" * 40 + "\tHEAD"

    monkeypatch.setattr(sources, "git", fake_git)
    register(client)
    created = client.post("/api/repositories", json={"source_type": "github", "source": GITHUB})
    assert created.status_code == 201, created.text
    assert created.json()["repository"]["branch"] == "develop"
    assert calls == [("ls-remote", "--symref", GITHUB, "HEAD")]


def test_github_repository_falls_back_to_main_when_head_is_unknown(client, monkeypatch):
    def unavailable(path, *args, **kwargs):
        raise sources.SourceError("Git operation failed")

    monkeypatch.setattr(sources, "git", unavailable)
    register(client)
    created = client.post("/api/repositories", json={"source_type": "github", "source": GITHUB})
    assert created.status_code == 201, created.text
    assert created.json()["repository"]["branch"] == "main"
