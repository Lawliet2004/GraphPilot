import hashlib
import io
import json
import os
import sys
import tarfile
from types import SimpleNamespace

import pytest

from scripts import cloud_backup


def archive(name="snapshots/source.py", kind=tarfile.REGTYPE):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as tar:
        entry = tarfile.TarInfo(name)
        entry.type = kind
        entry.linkname = "/outside" if kind in {tarfile.SYMTYPE, tarfile.LNKTYPE} else ""
        tar.addfile(entry, io.BytesIO())
    return output.getvalue()


@pytest.mark.parametrize(
    "name,kind",
    [
        ("../outside", tarfile.REGTYPE),
        ("/outside", tarfile.REGTYPE),
        ("link", tarfile.SYMTYPE),
        ("link", tarfile.LNKTYPE),
        ("pipe", tarfile.FIFOTYPE),
    ],
)
def test_archive_cannot_escape_target_or_create_special_files(name, kind):
    with pytest.raises(RuntimeError):
        cloud_backup.validate_archive(archive(name, kind))


@pytest.mark.parametrize(
    "project", ["postgres", "other-app", "../graphpilot-cloud-demo", "graphpilot-cloud-x;id"]
)
def test_unrelated_or_injected_project_is_rejected(project):
    with pytest.raises(ValueError):
        cloud_backup.validate_project(project)


def test_safe_owned_resource_and_archive():
    assert cloud_backup.validate_project("graphpilot-cloud-demo") == "graphpilot-cloud-demo"
    cloud_backup.validate_archive(archive())
    cloud_backup.require_ownership({"Labels": {"com.docker.compose.project": "owned"}}, "owned")
    with pytest.raises(RuntimeError):
        cloud_backup.require_ownership({"Labels": {"com.docker.compose.project": "other"}}, "owned")


def test_private_write_restricts_permissions_and_refuses_symlinks(tmp_path):
    path = tmp_path / "runtime.env"
    path.write_bytes(b"old")
    path.chmod(0o666)
    cloud_backup.private_write(path, b"private fixture")
    assert path.read_bytes() == b"private fixture"
    assert path.stat().st_mode & 0o777 == 0o600
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(OSError):
        cloud_backup.private_write(link, b"overwrite")
    assert path.read_bytes() == b"private fixture"


def test_restore_target_must_be_unused():
    with pytest.raises(RuntimeError):
        cloud_backup.require_fresh_target(
            lambda command: b"existing\n", "graphpilot-restore-fixture"
        )
    calls = []
    cloud_backup.require_fresh_target(
        lambda command: calls.append(command) or b"", "graphpilot-restore-fixture"
    )
    assert len(calls) == 2 and all(
        "label=com.docker.compose.project=graphpilot-restore-fixture" in call for call in calls
    )


@pytest.mark.parametrize("metadata", [[], {}, {"format_version": 1, "source_project": "other"}])
def test_invalid_backup_metadata_is_rejected(metadata):
    with pytest.raises(ValueError):
        cloud_backup.backup_metadata({"metadata.json": json.dumps(metadata).encode()})


def test_bundle_permissions_checksums_and_manifest_paths(tmp_path):
    tmp_path.chmod(0o700)
    payload = {
        name: b"fixture"
        for name in ["postgres.dump", "runtime.env", "fingerprint.json", "metadata.json"]
    }
    payload.update({"falkor.tar": archive(), "artifacts.tar": archive()})
    for name, data in payload.items():
        path = tmp_path / name
        path.write_bytes(data)
        path.chmod(0o600)
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    path.chmod(0o600)
    assert cloud_backup.load_backup(tmp_path) == payload
    path.chmod(0o644)
    with pytest.raises(ValueError):
        cloud_backup.load_backup(tmp_path)
    path.chmod(0o600)
    (tmp_path / "runtime.env").chmod(0o644)
    with pytest.raises(ValueError):
        cloud_backup.load_backup(tmp_path)
    (tmp_path / "runtime.env").chmod(0o600)
    (tmp_path / "postgres.dump").write_bytes(b"corrupted")
    with pytest.raises(ValueError):
        cloud_backup.load_backup(tmp_path)
    manifest["../outside"] = manifest.pop("postgres.dump")
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        cloud_backup.load_backup(tmp_path)


@pytest.mark.parametrize("resume_failure", [False, True])
def test_backup_failure_attempts_to_resume_every_owned_service(
    tmp_path, monkeypatch, capsys, resume_failure
):
    project = "graphpilot-cloud-owned"
    state = tmp_path / ".data/cloud-demo" / project
    state.mkdir(parents=True)
    (state / "compose.env").write_text("POSTGRES_DB=graphpilot\n")
    (state / "override.json").write_text("{}")
    monkeypatch.setattr(cloud_backup, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["cloud_backup.py", "--project", project])
    stopped, started = [], []

    def command(args, **kwargs):
        code, output = 0, b""
        if args[-3:] == ["ps", "--format", "json"]:
            output = b"\n".join(
                json.dumps({"Service": s, "State": "running"}).encode()
                for s in ["api", "worker", "web", "postgres", "falkordb"]
            )
        elif "ps" in args and "-q" in args:
            output = b"owned-container"
        elif args[:2] == ["docker", "inspect"]:
            output = json.dumps(
                [
                    {
                        "Image": "sha256:fixture",
                        "Config": {"Labels": {"com.docker.compose.project": project}},
                    }
                ]
            ).encode()
        elif "stop" in args:
            stopped.append(args[-1])
        elif "start" in args:
            started.append(args[-1])
            code = int(resume_failure and args[-1] == "worker")
        elif args[-1] == cloud_backup.FINGERPRINT:
            code = 1
        elif "from api.models import Job" in args[-1]:
            output = b"0\n"
        else:
            raise AssertionError("Unexpected command in bounded backup fixture")
        return SimpleNamespace(returncode=code, stdout=output, stderr=b"private failure text")

    monkeypatch.setattr(cloud_backup.subprocess, "run", command)
    previous = os.umask(0o077)
    try:
        with pytest.raises(RuntimeError):
            cloud_backup.main()
    finally:
        os.umask(previous)
    assert stopped == ["web", "api", "worker"]
    assert started == ["worker", "api", "web"]
    assert "private failure text" not in capsys.readouterr().out
    errors = list((tmp_path / ".data/backups").glob("*/last-error.txt"))
    assert len(errors) == 1 and errors[0].stat().st_mode & 0o077 == 0
