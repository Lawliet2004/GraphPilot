"""Audit every verified service image; incomplete evidence fails the release gate."""

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

TRIVY_IMAGE = (
    "aquasec/trivy:0.76.0@sha256:2416d1f74045b57274df1a340eee6b510cacd73c66a6ccb8da092b117eb7d222"
)
SERVICES = {"postgres", "falkordb", "migrate", "api", "worker", "web"}
SEVERITIES = {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
APP_PACKAGES = {"fastapi", "sqlalchemy", "falkordb", "psycopg"}


def verified_images(verification):
    if (
        not all(
            verification.get(key) is True
            for key in ("runtime_executed", "images_built_and_services_ready")
        )
        or verification.get("status") != "passed"
    ):
        raise ValueError("A successful container runtime verification is required")
    mapping = verification.get("service_images")
    if not isinstance(mapping, dict) or set(mapping) != SERVICES:
        raise ValueError("Every Compose service must have an observed image ID")
    if any(
        not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value)
        for value in mapping.values()
    ):
        raise ValueError("Full immutable Docker image IDs are required")
    images = sorted(set(mapping.values()))
    if verification.get("container_images") != images:
        raise ValueError("The image list must exactly cover the observed service images")
    return images


def assess(data, image, require_python=False):
    metadata = data.get("Metadata", {})
    os_info = metadata.get("OS") or {}
    if data.get("SchemaVersion") != 2 or metadata.get("ImageID") != image:
        raise ValueError("Scanner report does not identify the requested image")
    if os_info.get("Family") in {None, "", "none"} or not os_info.get("Name"):
        raise ValueError("Scanner did not identify the operating system")
    results = data.get("Results") or []
    if not any(r.get("Class") == "os-pkgs" and r.get("Packages") for r in results):
        raise ValueError("Scanner did not report an operating-system package inventory")
    python_packages = {
        p["Name"].lower().replace("_", "-")
        for r in results
        if r.get("Class") == "lang-pkgs" and r.get("Type") == "python-pkg"
        for p in r.get("Packages", [])
    }
    if require_python and not APP_PACKAGES.issubset(python_packages):
        raise ValueError("Scanner did not report the application's Python package inventory")
    if any(r.get("ExperimentalModifiedFindings") for r in results):
        raise ValueError("Suppressed or modified findings require review")
    findings = [v for r in results for v in r.get("Vulnerabilities", [])]
    if any(v.get("Severity") not in SEVERITIES for v in findings):
        raise ValueError("Scanner returned an unrecognized finding severity")
    counts = dict(Counter(v["Severity"] for v in findings))
    return {
        "status": "end_of_life"
        if os_info.get("EOSL")
        else "findings"
        if counts.get("HIGH", 0) + counts.get("CRITICAL", 0)
        else "passed",
        "image": image,
        "os": os_info,
        "severity_counts": counts,
        "os_package_count": sum(
            len(r.get("Packages", [])) for r in results if r.get("Class") == "os-pkgs"
        ),
        "python_inventory_required": require_python,
        "python_package_count": len(python_packages),
    }


def public_report(data):
    # ImageConfig can include environment variables. Publish package evidence only.
    return {
        "SchemaVersion": data.get("SchemaVersion"),
        "CreatedAt": data.get("CreatedAt"),
        "ArtifactType": data.get("ArtifactType"),
        "Metadata": {k: data.get("Metadata", {}).get(k) for k in ("ImageID", "OS")},
        "Results": data.get("Results", []),
    }


def audit(verification, output, scanner=None):
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "status": "incomplete",
        "scope": "Exact locally built/service image IDs from the disposable Compose verification",
        "scanner": str(scanner) if scanner else TRIVY_IMAGE,
        "images": [],
    }
    try:
        images = verified_images(verification)
        docker = shutil.which("docker")
        if not scanner and not docker:
            raise ValueError("Docker is required to run the pinned scanner")
        # A caller's TRIVY_* settings must not narrow scans or suppress findings.
        env = {k: v for k, v in os.environ.items() if not k.startswith("TRIVY_")}
        cache = output.parent / "cache"
        cache.mkdir(exist_ok=True)
        run_dir = output.parent / ("run-" + uuid.uuid4().hex[:12])
        run_dir.mkdir()
        with tempfile.TemporaryDirectory(prefix="graphpilot-image-audit-") as directory:
            private = Path(directory)
            for index, image in enumerate(images):
                raw = private / f"image-{index}.json"
                destination = run_dir / raw.name
                log = run_dir / f"image-{index}.log"
                name = "graphpilot_audit_" + uuid.uuid4().hex[:12]
                command = (
                    [str(scanner)]
                    if scanner
                    else [
                        docker,
                        "run",
                        "--rm",
                        "--name",
                        name,
                        "--mount",
                        "type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock,readonly",
                        "--mount",
                        f"type=bind,source={private},target=/reports",
                        "--mount",
                        f"type=bind,source={cache},target=/root/.cache/trivy",
                        TRIVY_IMAGE,
                    ]
                ) + [
                    "image",
                    "--image-src",
                    "docker",
                    "--config",
                    "",
                    "--ignorefile",
                    "",
                    "--scanners",
                    "vuln",
                    "--pkg-types",
                    "os,library",
                    "--severity",
                    ",".join(sorted(SEVERITIES)),
                    "--ignore-unfixed=false",
                    "--list-all-pkgs",
                    "--exit-code",
                    "0",
                    "--exit-on-eol",
                    "0",
                    "--timeout",
                    "10m",
                    "--format",
                    "json",
                    "--output",
                    str(raw) if scanner else "/reports/" + raw.name,
                    image,
                ]
                row = {"image": image, "status": "scanner_failed"}
                print(f"Auditing image {index + 1}/{len(images)}: {image}", flush=True)
                try:
                    with log.open("wb") as stream:
                        os.chmod(log, 0o600)
                        completed = subprocess.run(
                            command, env=env, stdout=stream, stderr=stream, timeout=615
                        )
                    if completed.returncode != 0:
                        row["exit_code"] = completed.returncode
                    else:
                        data = json.loads(raw.read_text())
                        destination.write_text(json.dumps(public_report(data), indent=2) + "\n")
                        row = assess(
                            data,
                            image,
                            require_python=image
                            in {
                                verification["service_images"][s]
                                for s in ("api", "worker", "migrate")
                            },
                        )
                        row["report"] = str(destination.relative_to(output.parent))
                except subprocess.TimeoutExpired:
                    row["status"] = "timed_out"
                except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
                    row.update(status="invalid_report", error_type=type(exc).__name__)
                finally:
                    if not scanner:
                        try:
                            subprocess.run(
                                [docker, "rm", "--force", name],
                                env=env,
                                capture_output=True,
                                timeout=15,
                                check=False,
                            )
                        except (OSError, subprocess.TimeoutExpired):
                            row["status"] = "scanner_cleanup_failed"
                report["images"].append(row)
                output.write_text(json.dumps(report, indent=2) + "\n")
        report["status"] = (
            "passed" if all(r["status"] == "passed" for r in report["images"]) else "failed"
        )
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        report.update(status="invalid_verification", error_type=type(exc).__name__)
    finally:
        output.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verification", type=Path, default=Path(".data/ci/container.json"))
    parser.add_argument("--output", type=Path, default=Path(".data/ci/image-audit/summary.json"))
    parser.add_argument(
        "--trivy", type=Path, help="Use a native Trivy executable with local Docker"
    )
    args = parser.parse_args()
    try:
        verification = json.loads(args.verification.read_text())
    except (OSError, ValueError):
        verification = {}
    result = audit(verification, args.output, args.trivy.resolve() if args.trivy else None)
    print(json.dumps(result, indent=2))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
