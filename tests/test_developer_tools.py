import json
import os
import stat
import subprocess
import sys

import httpx
import pytest

from api import client


def run_cli(*argv):
    sys.argv = ["graphpilot", *[str(a) for a in argv]]
    return client.main()


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["graphpilot"])

    def invoke(*argv):
        return run_cli(*argv)

    return invoke


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.name", "Test Dev")
    git(path, "config", "user.email", "dev@example.com")
    (path / "seed.txt").write_text("seed\n")
    git(path, "add", "seed.txt")
    git(path, "commit", "-m", "initial")
    return path


def write_session(tmp_path):
    path = tmp_path / "cfg" / "session.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "server": "https://graphpilot.example",
                "token": "gp_mcp_" + "a" * 40,
                "id": "cli-1",
                "expires_at": 9999999999,
                "scopes": ["read"],
            }
        )
    )
    os.chmod(path, 0o600)
    return path


def mock_http(monkeypatch, handler):
    real_client = httpx.Client
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=transport, **kw))


REPO = "11111111-2222-3333-4444-555555555555"
JOB = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
REVISION = "00000000-1111-2222-3333-444444444444"


# --- hosted ask/jobs ---------------------------------------------------------


def test_ask_dispatches_context_request(cli, monkeypatch, tmp_path, capsys):
    session = write_session(tmp_path)
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json={"answer": "done", "citations": []})

    mock_http(monkeypatch, handler)
    rc = cli(
        "--config",
        session,
        "ask",
        REPO,
        "How does auth work?",
        "--branch",
        "main",
        "--revision",
        REVISION,
    )
    assert rc == 0
    assert seen["method"] == "POST"
    assert seen["path"] == f"/api/repositories/{REPO}/context"
    assert seen["params"] == {"branch": "main", "revision": REVISION}
    assert seen["body"] == {"question": "How does auth work?"}
    assert '"answer": "done"' in capsys.readouterr().out


def test_ask_trims_and_omits_optional_params(cli, monkeypatch, tmp_path):
    session = write_session(tmp_path)
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json={"answer": None})

    mock_http(monkeypatch, handler)
    assert cli("--config", session, "ask", REPO, "  Where is the worker?  ") == 0
    assert seen["params"] == {}
    assert seen["body"] == {"question": "Where is the worker?"}


def test_ask_and_jobs_reject_non_uuid_identifiers(cli, monkeypatch, tmp_path):
    session = write_session(tmp_path)
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={})

    mock_http(monkeypatch, handler)
    for bad in [
        "not-a-uuid",
        "../" + REPO,
        REPO + "/extra",
        "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
    ]:
        with pytest.raises(SystemExit):
            cli("--config", session, "ask", bad, "Is this fine?")
    for bad in ["job-7", "../../etc", JOB + "0"]:
        with pytest.raises(SystemExit):
            cli("--config", session, "jobs", "cancel", bad)
    with pytest.raises(SystemExit):
        cli("--config", session, "ask", REPO, "q?", "--revision", "abc123")
    assert calls == []


def test_ask_requires_session(cli, tmp_path):
    missing = tmp_path / "no" / "session.json"
    assert cli("--config", missing, "ask", REPO, "Where is the worker?") == 1


def test_jobs_list_and_cancel_dispatch(cli, monkeypatch, tmp_path, capsys):
    session = write_session(tmp_path)
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={"id": JOB, "status": "queued"})

    mock_http(monkeypatch, handler)
    assert cli("--config", session, "jobs", "list", REPO) == 0
    assert cli("--config", session, "jobs", "cancel", JOB) == 0
    assert calls == [
        ("GET", f"/api/repositories/{REPO}/jobs"),
        ("POST", f"/api/jobs/{JOB}/cancel"),
    ]
    assert f'"id": "{JOB}"' in capsys.readouterr().out


# --- local git workflow -------------------------------------------------------


def test_git_daily_reports_branch_and_history(cli, repo, capsys):
    assert cli("git", "daily", "--path", repo) == 0
    out = capsys.readouterr().out
    assert "branch: main" in out
    assert "status: clean" in out
    assert "upstream: none configured" in out
    assert "initial" in out


def test_git_status_and_dirty_report(cli, repo, capsys):
    (repo / "new.txt").write_text("x")
    assert cli("git", "status", "--path", repo) == 0
    assert "?? new.txt" in capsys.readouterr().out
    assert cli("git", "daily", "--path", repo) == 0
    assert "1 changed file(s)" in capsys.readouterr().out


def test_git_stage_commit_and_log(cli, repo, capsys):
    (repo / "a.txt").write_text("a")
    (repo / "b.txt").write_text("b")
    assert cli("git", "stage", "a.txt", "--path", repo) == 0
    assert cli("git", "commit", "--message", "add a", "--path", repo) == 0
    names = git(repo, "ls-tree", "--name-only", "HEAD").stdout.split()
    assert "a.txt" in names and "b.txt" not in names
    assert cli("git", "log", "--path", repo) == 0
    assert "add a" in capsys.readouterr().out


def test_git_stage_rejects_outside_and_dotgit(cli, repo, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("nope")
    assert cli("git", "stage", "../outside.txt", "--path", repo) == 1
    assert cli("git", "stage", outside, "--path", repo) == 1
    assert cli("git", "stage", ".git/config", "--path", repo) == 1
    assert cli("git", "stage", "--path", repo, "--", "-u") == 1


def test_git_stage_relative_to_subdirectory_path(cli, repo):
    sub = repo / "sub dir"
    sub.mkdir()
    (sub / "my file.txt").write_text("x")
    assert cli("git", "stage", "my file.txt", "--path", sub) == 0
    staged = git(repo, "diff", "--cached", "--name-only").stdout.splitlines()
    assert staged == ["sub dir/my file.txt"]


def test_git_stage_symlink_stages_link_not_target(cli, repo, tmp_path):
    os.symlink("seed.txt", repo / "link.txt")
    assert cli("git", "stage", "link.txt", "--path", repo) == 0
    mode = git(repo, "ls-files", "-s", "link.txt").stdout
    assert mode.startswith("120000")
    outside = tmp_path / "escape-target.txt"
    outside.write_text("nope")
    os.symlink(str(outside), repo / "escape.txt")
    assert cli("git", "stage", "escape.txt", "--path", repo) == 1


def test_git_stage_uses_literal_pathspecs(cli, repo):
    (repo / "star*.txt").write_text("s")
    (repo / "starX.txt").write_text("s")
    assert cli("git", "stage", "star*.txt", "--path", repo) == 0
    staged = git(repo, "diff", "--cached", "--name-only").stdout.splitlines()
    assert staged == ["star*.txt"]
    assert "?? starX.txt" in git(repo, "status", "--porcelain").stdout


def test_git_switch_validates_refs(cli, repo, capsys):
    assert cli("git", "switch", "--create", "feature", "--path", repo) == 0
    assert git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip() == "feature"
    assert cli("git", "switch", "main", "--path", repo) == 0
    assert cli("git", "switch", "--path", repo, "--", "-d") == 1
    assert cli("git", "switch", "bad..name", "--path", repo) == 1
    assert cli("git", "switch", "x.lock", "--path", repo) == 1


def test_git_push_and_pull_argv_are_fixed(cli, repo, monkeypatch):
    calls = []
    real_run = subprocess.run
    root = os.path.realpath(repo)

    def recording(argv, **kwargs):
        calls.append(list(argv))
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording)
    cli("git", "push", "--path", repo)
    cli("git", "pull", "--path", repo)
    pushes = [c for c in calls if c[:4] == ["git", "-C", root, "push"]]
    pulls = [c for c in calls if c[:4] == ["git", "-C", root, "pull"]]
    assert pushes == [["git", "-C", root, "push"]]
    assert pulls == [["git", "-C", root, "pull", "--ff-only"]]


def test_git_commit_never_passes_flags(cli, repo, monkeypatch):
    calls = []
    real_run = subprocess.run
    root = os.path.realpath(repo)

    def recording(argv, **kwargs):
        calls.append(list(argv))
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording)
    (repo / "c.txt").write_text("c")
    cli("git", "stage", "c.txt", "--path", repo)
    assert cli("git", "commit", "--message", "tracked", "--path", repo) == 0
    commits = [c for c in calls if "commit" in c]
    assert commits[-1] == ["git", "-C", root, "commit", "--message", "tracked"]


def test_git_rejects_non_repository(cli, tmp_path, capsys):
    assert cli("git", "daily", "--path", tmp_path) == 1
    assert cli("git", "status", "--path", tmp_path / "missing") == 1
    assert "Not a directory" in capsys.readouterr().err or "work tree" in capsys.readouterr().err


def test_git_commands_need_no_session(cli, repo, tmp_path, capsys):
    missing = tmp_path / "cfg" / "session.json"
    assert cli("--config", missing, "git", "status", "--path", repo) == 0
    assert not missing.exists()


# --- runner profiles ----------------------------------------------------------


def configure(cli, cfg, name, codespace, workspace=None):
    argv = ["--config", cfg, "runner", "configure", name, "--codespace", codespace]
    if workspace:
        argv += ["--workspace", workspace]
    assert cli(*argv) == 0


def test_configure_stores_private_profile(cli, tmp_path, capsys):
    cfg = tmp_path / "c" / "session.json"
    assert (
        cli(
            "--config",
            cfg,
            "runner",
            "configure",
            "demo",
            "--codespace",
            "my-codespace-1",
        )
        == 0
    )
    path = cfg.parent / "runners.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) & 0o077 == 0
    data = json.loads(path.read_text())
    assert data["profiles"]["demo"] == {
        "codespace": "my-codespace-1",
        "workspace": "/workspaces/GraphPilot",
    }
    assert "token" not in path.read_text()


def test_configure_validates_inputs(cli, tmp_path):
    cfg = tmp_path / "c" / "session.json"
    bad = [
        ("runner", "configure", "demo", "--codespace", "Bad Name"),
        ("runner", "configure", "demo", "--codespace=-lead"),
        ("runner", "configure", "demo", "--codespace", "ok-1", "--workspace", "relative"),
        ("runner", "configure", "demo", "--codespace", "ok-1", "--workspace", "/a/../b"),
        ("runner", "configure", "bad name!", "--codespace", "ok-1"),
    ]
    for argv in bad:
        assert cli("--config", cfg, *argv) == 1, argv
    assert not (cfg.parent / "runners.json").exists()


def test_profiles_require_private_file(cli, tmp_path, capsys):
    cfg = tmp_path / "c" / "session.json"
    cfg.parent.mkdir(parents=True)
    path = cfg.parent / "runners.json"
    path.write_text(json.dumps({"profiles": {}}))
    os.chmod(path, 0o644)
    assert cli("--config", cfg, "runner", "list") == 1
    assert "private regular file" in capsys.readouterr().err


def test_runner_list_needs_no_session(cli, tmp_path, capsys):
    cfg = tmp_path / "c" / "session.json"
    assert cli("--config", cfg, "runner", "list") == 0
    assert json.loads(capsys.readouterr().out) == {}
    assert not cfg.exists()


def test_runner_profile_parse_error_hides_contents(cli, tmp_path, capsys):
    cfg = tmp_path / "c" / "session.json"
    cfg.parent.mkdir(parents=True)
    path = cfg.parent / "runners.json"
    path.write_text("{ gp_mcp_SENTINELSECRET never valid json")
    os.chmod(path, 0o600)
    assert cli("--config", cfg, "runner", "list") == 1
    assert "SENTINELSECRET" not in capsys.readouterr().err


# --- runner lifecycle via gh ---------------------------------------------------


def fake_gh(monkeypatch, respond):
    calls = []

    def run(argv, **kwargs):
        calls.append(list(argv))
        outcome = respond(list(argv))
        if isinstance(outcome, BaseException):
            raise outcome
        return subprocess.CompletedProcess(
            argv, outcome.get("rc", 0), outcome.get("stdout", ""), outcome.get("stderr", "")
        )

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_runner_start_uses_gh_api(cli, tmp_path, monkeypatch):
    cfg = tmp_path / "c" / "session.json"
    configure(cli, cfg, "demo", "my-cs-1")
    calls = fake_gh(monkeypatch, lambda argv: {"rc": 0})
    assert cli("--config", cfg, "runner", "start", "demo") == 0
    assert calls == [["gh", "api", "-X", "POST", "/user/codespaces/my-cs-1/start", "--silent"]]


def test_runner_stop_only_targets_stored_profile(cli, tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "c" / "session.json"
    configure(cli, cfg, "demo", "my-cs-1")
    calls = fake_gh(monkeypatch, lambda argv: {"rc": 0})
    assert cli("--config", cfg, "runner", "stop", "stray-codespace") == 1
    assert calls == []
    assert cli("--config", cfg, "runner", "stop", "demo") == 0
    assert calls == [["gh", "codespace", "stop", "-c", "my-cs-1"]]


def test_runner_ambiguous_name_requires_choice(cli, tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "c" / "session.json"
    configure(cli, cfg, "one", "cs-one-1")
    configure(cli, cfg, "two", "cs-two-1")
    calls = fake_gh(monkeypatch, lambda argv: {"rc": 0})
    assert cli("--config", cfg, "runner", "stop") == 1
    assert "specify NAME" in capsys.readouterr().err
    assert calls == []


def _gh_listing(state="Available", name="my-cs-1"):
    return {"rc": 0, "stdout": json.dumps([{"name": name, "state": state}])}


def _gh_respond(listing):
    def respond(argv):
        if "list" in argv:
            return listing
        return {"rc": 0}

    return respond


def test_runner_status_filters_by_codespace(cli, tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "c" / "session.json"
    configure(cli, cfg, "demo", "my-cs-1")
    configure(cli, cfg, "other", "other-cs-2")
    listing = [
        {"name": "my-cs-1", "state": "Available", "repository": "me/GraphPilot"},
        {"name": "unrelated", "state": "Shutdown", "repository": "me/other"},
    ]
    calls = fake_gh(monkeypatch, lambda argv: {"rc": 0, "stdout": json.dumps(listing)})
    capsys.readouterr()
    assert cli("--config", cfg, "runner", "status") == 0
    assert calls == [["gh", "codespace", "list", "--json", "name,state,repository,gitStatus"]]
    out = json.loads(capsys.readouterr().out)
    assert out["runners"] == [
        {
            "name": "my-cs-1",
            "state": "Available",
            "repository": "me/GraphPilot",
            "profile": "demo",
        }
    ]
    assert out["not_found"] == ["other"]


def test_runner_check_runs_fixed_commands(cli, tmp_path, monkeypatch):
    cfg = tmp_path / "c" / "session.json"
    configure(cli, cfg, "demo", "my-cs-1")
    calls = fake_gh(monkeypatch, _gh_respond(_gh_listing()))
    assert cli("--config", cfg, "runner", "check", "demo") == 0
    assert calls == [
        ["gh", "codespace", "list", "--json", "name,state"],
        [
            "gh",
            "codespace",
            "ssh",
            "-c",
            "my-cs-1",
            "--",
            "cd /workspaces/GraphPilot && "
            "python3 scripts/cloud_demo.py status && "
            "python3 scripts/cloud_demo.py check",
        ],
    ]


def test_runner_check_and_logs_never_wake_stopped_runner(cli, tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "c" / "session.json"
    configure(cli, cfg, "demo", "my-cs-1")
    calls = fake_gh(monkeypatch, _gh_respond(_gh_listing(state="Shutdown")))
    assert cli("--config", cfg, "runner", "check", "demo") == 1
    assert cli("--config", cfg, "runner", "logs", "demo") == 1
    list_argv = ["gh", "codespace", "list", "--json", "name,state"]
    assert calls == [list_argv, list_argv]  # never an SSH call on a stopped runner
    err = capsys.readouterr().err
    assert "runner start demo" in err and "Shutdown" in err


def test_runner_check_unknown_codespace_errors_without_ssh(cli, tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "c" / "session.json"
    configure(cli, cfg, "demo", "my-cs-1")
    calls = fake_gh(monkeypatch, _gh_respond({"rc": 0, "stdout": "[]"}))
    assert cli("--config", cfg, "runner", "check", "demo") == 1
    assert calls == [["gh", "codespace", "list", "--json", "name,state"]]
    assert "not visible" in capsys.readouterr().err


def test_runner_logs_bounded_compose_command(cli, tmp_path, monkeypatch):
    cfg = tmp_path / "c" / "session.json"
    configure(cli, cfg, "demo", "my-cs-1", "/workspaces/GraphPilot")
    calls = fake_gh(monkeypatch, _gh_respond(_gh_listing()))
    assert (
        cli(
            "--config",
            cfg,
            "runner",
            "logs",
            "demo",
            "--service",
            "api",
            "--lines",
            "50",
        )
        == 0
    )
    assert calls[0] == ["gh", "codespace", "list", "--json", "name,state"]
    remote = calls[1][-1]
    assert calls[1][:5] == ["gh", "codespace", "ssh", "-c", "my-cs-1"]
    assert remote.startswith("cd /workspaces/GraphPilot && docker compose ")
    assert "--env-file .data/cloud-demo/graphpilot-cloud-demo/compose.env" in remote
    assert remote.endswith("logs --no-color --tail 50 api")
    assert "POSTGRES_PASSWORD" not in remote and "=" not in remote.split("compose", 1)[1]


def test_runner_ssh_interactive(cli, tmp_path, monkeypatch):
    cfg = tmp_path / "c" / "session.json"
    configure(cli, cfg, "demo", "my-cs-1")
    calls = fake_gh(monkeypatch, lambda argv: {"rc": 0})
    assert cli("--config", cfg, "runner", "ssh", "demo") == 0
    assert calls == [["gh", "codespace", "ssh", "-c", "my-cs-1"]]


def test_runner_missing_and_expired_gh(cli, tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "c" / "session.json"
    configure(cli, cfg, "demo", "my-cs-1")
    fake_gh(monkeypatch, lambda argv: FileNotFoundError("gh"))
    assert cli("--config", cfg, "runner", "status", "demo") == 1
    assert "gh auth login" in capsys.readouterr().err
    fake_gh(
        monkeypatch,
        lambda argv: {"rc": 1, "stderr": "HTTP 401: Bad credentials. Try 'gh auth login'."},
    )
    assert cli("--config", cfg, "runner", "start", "demo") == 1
    assert "gh auth login" in capsys.readouterr().err
    fake_gh(monkeypatch, lambda argv: {"rc": 1, "stderr": "boom"})
    assert cli("--config", cfg, "runner", "stop", "demo") == 1
    assert "boom" in capsys.readouterr().err


def test_gh_error_text_is_sanitized(cli, tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "c" / "session.json"
    configure(cli, cfg, "demo", "my-cs-1")
    sentinel = (
        "fatal: https://user:ghp_SENTINELTOKEN1234567890@github.com/x failed "
        "?token=s3cr3tSENTINEL&other=ok Bearer gp_mcp_SENTINELBEARER0000"
    )
    fake_gh(monkeypatch, lambda argv: {"rc": 1, "stderr": sentinel})
    assert cli("--config", cfg, "runner", "stop", "demo") == 1
    err = capsys.readouterr().err
    for leaked in ("ghp_SENTINELTOKEN1234567890", "s3cr3tSENTINEL", "gp_mcp_SENTINELBEARER0000"):
        assert leaked not in err
    assert "***@" in err and "token=REDACTED" in err


def test_git_error_text_is_sanitized(cli, repo, monkeypatch, capsys):
    calls = []
    real_run = subprocess.run

    def hostile(argv, **kwargs):
        calls.append(list(argv))
        if argv[3] == "pull":
            return subprocess.CompletedProcess(
                argv,
                1,
                "",
                "fatal: https://u:ghp_SENTINEL7777777777777777@github.com/x?key=k1SENTINEL",
            )
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", hostile)
    assert cli("git", "pull", "--path", repo) == 1
    err = capsys.readouterr().err
    assert "ghp_SENTINEL7777777777777777" not in err
    assert "k1SENTINEL" not in err
    assert "***@" in err


def test_help_needs_no_network(capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli("--help")
    assert exc.value.code == 0
    with pytest.raises(SystemExit) as exc:
        run_cli("git", "--help")
    assert exc.value.code == 0
