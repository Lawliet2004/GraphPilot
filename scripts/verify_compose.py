"""Owned, disposable Compose image/start/recreation/volume-restore verification.

--check-config works without a daemon. Runtime mode never uses the normal .env,
project name, volumes or port, and deletes only its randomly named deployment.
Private backup bytes remain in a temporary ignored directory until cleanup.
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

from scripts.audit_container_images import SERVICES
from scripts.smoke_gateway import exercise, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("docs/CONTAINER_VERIFICATION.json"))
    args = parser.parse_args()
    if not __debug__:
        parser.error("Verification requires assertions; run Python without -O")
    docker = shutil.which("docker")
    standalone = Path(".tools/docker-compose").resolve()
    if not docker and not (args.check_config and standalone.is_file()):
        parser.error("Docker Engine + Compose are required; no runtime check was executed")
    compose = [docker, "compose"] if docker else [str(standalone)]
    project = "graphpilot_verify_" + uuid.uuid4().hex[:12]
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "status": "not_run",
        "project": project,
        "runtime_executed": False,
        "image_audit_executed": False,
        "scope": "Disposable Compose verification; no public TLS, SMTP, model or remote CI claim",
    }
    parent = Path(".data/compose-verification").resolve()
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix=project, dir=parent) as directory:
        root = Path(directory)
        os.chmod(root, 0o700)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        password = secrets.token_hex(32)
        dsn = f"postgresql+psycopg://graphpilot:{password}@postgres:5432/graphpilot"
        config = root / "probe.env"
        config.write_text(
            "\n".join(
                [
                    "POSTGRES_USER=graphpilot",
                    "POSTGRES_DB=graphpilot",
                    f"POSTGRES_PASSWORD={password}",
                    f"GP_COMPOSE_DATABASE_URL={dsn}",
                    f"GP_DATABASE_URL={dsn}",
                    "GP_ENVIRONMENT=test",
                    f"GP_PUBLIC_URL={origin}",
                    f"GP_ORIGINS={json.dumps([origin])}",
                    "GP_COOKIE_SECURE=false",
                    "GP_ALLOWED_LOCAL_ROOTS=[]",
                    "GP_DATA_DIR=/data",
                    "GP_LLM_BASE_URL=",
                    "GP_LLM_MODEL=",
                    "GP_LLM_API_KEY=",
                    "GP_GITHUB_TOKEN=",
                    "GP_SMTP_HOST=",
                    "GP_SMTP_FROM=",
                    "GP_FALKOR_SOCKET=",
                    "GP_FALKOR_PASSWORD=",
                ]
            )
            + "\n"
        )
        os.chmod(config, 0o600)
        env = {
            **os.environ,
            "GP_ENV_FILE": str(config),
            "GP_WEB_PORT": str(port),
            "POSTGRES_USER": "graphpilot",
            "POSTGRES_DB": "graphpilot",
            "POSTGRES_PASSWORD": password,
            "GP_COMPOSE_DATABASE_URL": dsn,
        }
        command = compose + [
            "--env-file",
            str(config),
            "--project-name",
            project,
            "--file",
            str(Path("docker-compose.yml").resolve()),
        ]
        with (root / "commands.log").open("wb") as logs:
            os.chmod(root / "commands.log", 0o600)

            def run(*arguments, output=None, input_file=None, raw=False):
                report["last_operation"] = ("docker " if raw else "compose ") + " ".join(
                    arguments[:2]
                )
                return subprocess.run(
                    ([docker] if raw else command) + list(arguments),
                    env=env,
                    check=True,
                    stdout=output or logs,
                    stderr=logs,
                    stdin=input_file,
                    timeout=600,
                )

            started = False
            try:
                run("config", "--quiet")
                report["compose_configuration_valid"] = True
                configured_services = subprocess.check_output(
                    command + ["config", "--services"], env=env, text=True
                ).split()
                assert set(configured_services) == SERVICES, (
                    "Update audit coverage for changed services"
                )
                report["compose_services"] = sorted(configured_services)
                if args.check_config:
                    report["status"] = "configuration_only"
                    return
                run("info", "--format", "{{.ServerVersion}}", raw=True)
                # No project with this generated name may already contain containers.
                existing = subprocess.check_output(command + ["ps", "-aq"], env=env)
                assert not existing.strip(), "Refuse to reuse an existing Compose project"
                started = True
                report.update(status="failed", runtime_executed=True)
                print("Building and starting the disposable Compose deployment", flush=True)
                run("up", "--build", "-d", "--wait", "--wait-timeout", "180")
                report["images_built_and_services_ready"] = True
                run(
                    "exec",
                    "-T",
                    "postgres",
                    "sh",
                    "-c",
                    'test "$(id -u)" != 0 && ! command -v gosu',
                )
                report["postgres_nonroot_and_root_helper_absent"] = True
                report["service_images"] = {}
                for service in sorted(SERVICES):
                    container = subprocess.check_output(
                        command + ["ps", "--all", "-q", service], env=env, text=True
                    ).strip()
                    assert container and len(container.splitlines()) == 1
                    report["service_images"][service] = subprocess.check_output(
                        [docker, "inspect", "--format", "{{.Image}}", container], env=env, text=True
                    ).strip()
                report["container_images"] = sorted(set(report["service_images"].values()))
                for service, container_port in (("postgres", "5432/tcp"), ("falkordb", "6379/tcp")):
                    container = subprocess.check_output(
                        command + ["ps", "-q", service], env=env, text=True
                    ).strip()
                    bindings = json.loads(
                        subprocess.check_output(
                            [
                                docker,
                                "inspect",
                                "--format",
                                "{{json .NetworkSettings.Ports}}",
                                container,
                            ],
                            env=env,
                            text=True,
                        )
                    )
                    assert not bindings.get(container_port), "Database has a published host port"
                internal = subprocess.check_output(
                    [
                        docker,
                        "network",
                        "inspect",
                        project + "_private",
                        "--format",
                        "{{.Internal}}",
                    ],
                    env=env,
                    text=True,
                ).strip()
                assert internal == "true"
                report["database_ports_private_and_network_internal"] = True
                image = subprocess.check_output(
                    command + ["images", "-q", "api"], env=env, text=True
                ).strip()
                assert image and len(image.splitlines()) == 1

                def wait(client):
                    deadline = time.monotonic() + 60
                    while time.monotonic() < deadline:
                        try:
                            if client.get("/api/health/ready", timeout=2).status_code == 200:
                                return
                        except httpx.HTTPError:
                            pass
                        time.sleep(0.2)
                    raise RuntimeError("Compose gateway did not recover")

                def volume(name, archive, restore=False):
                    volume_name = project + "_" + name
                    owner = subprocess.check_output(
                        [
                            docker,
                            "volume",
                            "inspect",
                            "--format",
                            '{{ index .Labels "com.docker.compose.project" }}',
                            volume_name,
                        ],
                        env=env,
                        text=True,
                    ).strip()
                    assert owner == project, "Refuse a volume outside this verification project"
                    if restore:
                        code = """import sys,tarfile
def safe(member,destination):
 item=tarfile.data_filter(member,destination)
 return item.replace(uid=member.uid,gid=member.gid) if item else None
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz') as archive:
 archive.extractall('/data',filter=safe)
"""
                    else:
                        code = "import sys,tarfile; t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz'); t.add('/data',arcname='.'); t.close()"
                    mount = f"type=volume,source={volume_name},target=/data" + (
                        "" if restore else ",readonly"
                    )
                    with archive.open("rb" if restore else "wb") as stream:
                        os.chmod(archive, 0o600)
                        helper = project + "_volume_" + name
                        try:
                            run(
                                "run",
                                "--rm",
                                "--name",
                                helper,
                                "--label",
                                "graphpilot.verification=" + project,
                                "--network",
                                "none",
                                "--user",
                                "0",
                                "-i",
                                "--mount",
                                mount,
                                "--entrypoint",
                                "python",
                                image,
                                "-c",
                                code,
                                input_file=stream if restore else None,
                                output=None if restore else stream,
                                raw=True,
                            )
                        except subprocess.CalledProcessError:
                            logs.flush()
                            errors = re.findall(
                                rb"(?:^|\n)([A-Za-z_][A-Za-z_0-9.]*Error):",
                                (root / "commands.log").read_bytes()[-16000:],
                            )
                            if errors:
                                report["volume_helper_error_type"] = errors[-1].decode()
                            raise
                        finally:
                            # A killed Docker client can leave its --rm helper running.
                            subprocess.run(
                                [docker, "rm", "--force", helper],
                                env=env,
                                stdout=logs,
                                stderr=logs,
                                timeout=15,
                                check=False,
                            )

                def restart(client):
                    print("Checking API recreation and private volume backup/restore", flush=True)
                    run("up", "-d", "--no-deps", "--force-recreate", "api")
                    wait(client)
                    expect(client.get("/api/auth/session"), 200)
                    report["api_recreation_gateway_recovery"] = True
                    run("stop", "web", "api", "worker")
                    dump = root / "postgres.dump"
                    with dump.open("wb") as stream:
                        os.chmod(dump, 0o600)
                        run(
                            "exec",
                            "-T",
                            "postgres",
                            "sh",
                            "-c",
                            'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc',
                            output=stream,
                        )
                    run("exec", "-T", "falkordb", "redis-cli", "SAVE")
                    run("stop", "falkordb")
                    graph, artifacts = root / "falkor.tar.gz", root / "artifacts.tar.gz"
                    volume("falkor_data", graph)
                    volume("artifacts", artifacts)
                    report["backup_sha256"] = {
                        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (dump, graph, artifacts)
                    }
                    run("down", "--volumes", "--remove-orphans")
                    run("create", "postgres", "falkordb", "api")
                    volume("falkor_data", graph, restore=True)
                    volume("artifacts", artifacts, restore=True)
                    run("up", "-d", "--wait", "postgres")
                    with dump.open("rb") as stream:
                        run(
                            "exec",
                            "-T",
                            "postgres",
                            "sh",
                            "-c",
                            'pg_restore --no-owner --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
                            input_file=stream,
                        )
                    run("up", "-d", "--wait", "--wait-timeout", "180")
                    wait(client)
                    report["owned_volumes_backed_up_and_restored"] = True

                with httpx.Client(
                    base_url=origin, headers={"Origin": origin}, timeout=45, trust_env=False
                ) as client:
                    exercise(client, report, restart)
                report["status"] = "passed"
            except Exception as exc:
                report["failure_operation"] = report.get("last_operation")
                report["failure_type"] = type(exc).__name__
                raise
            finally:
                try:
                    if started:
                        run("down", "--volumes", "--remove-orphans")
                        report["owned_deployment_removed"] = True
                except Exception as exc:
                    report.update(status="cleanup_failed", cleanup_error_type=type(exc).__name__)
                    raise
                finally:
                    if report["status"] not in {"passed", "configuration_only"}:
                        rescue = parent / ("failed-" + project)
                        rescue.mkdir(mode=0o700)
                        logs.flush()
                        shutil.copy2(root / "commands.log", rescue / "commands.log")
                        report["private_failure_log"] = str(rescue / "commands.log")
                        if report["status"] == "cleanup_failed":
                            shutil.copy2(config, rescue / "probe.env")
                            report["private_recovery_environment"] = str(rescue / "probe.env")
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(json.dumps(report, indent=2) + "\n")
                    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
