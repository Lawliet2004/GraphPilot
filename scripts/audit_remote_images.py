"""Audit published runtime bases/services without a container daemon.

This cannot audit GraphPilot images that have not been built. Credentials are not
needed: the selected image metadata references only public upstream images.
"""

import argparse
import json
import os
import subprocess
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

RUNTIME_REPOS = {
    "library/postgres",
    "library/python",
    "library/nginx",
    "falkordb/falkordb",
    "falkordb/falkordb-server",
}


def runtime_images(metadata):
    selected = [
        row
        for row in metadata["images"]
        if row["image"].split("@")[0].split(":")[0] in RUNTIME_REPOS
    ]
    if not selected:
        raise ValueError("Metadata has no supported runtime images to audit")
    return selected


def scan(command, output, run_dir, index, env, timeout):
    deadline = time.monotonic() + timeout
    attempts = []
    for attempt in range(2):
        remaining = max(1, int(deadline - time.monotonic()))
        log_path = run_dir / f"image-{index}-attempt-{attempt + 1}.log"
        with log_path.open("wb") as log:
            os.chmod(log_path, 0o600)
            try:
                result = subprocess.run(
                    command, env=env, stdout=log, stderr=log, timeout=remaining + 15
                )
            except subprocess.TimeoutExpired:
                return {"status": "timed_out", "attempts": attempts, "private_log": str(log_path)}
        if result.returncode == 0 and output.is_file():
            return {"status": "completed", "attempts": attempts}
        message = log_path.read_text(errors="replace").lower()
        transient = any(
            term in message
            for term in (
                "tls handshake timeout",
                "connection reset",
                "timeout awaiting response headers",
            )
        )
        attempts.append(
            {
                "exit_code": result.returncode,
                "error_category": "transient_transport" if transient else "scanner_error",
                "private_log": str(log_path),
            }
        )
        if not transient or time.monotonic() + 2 >= deadline:
            break
        print("Retrying transient registry transport failure", flush=True)
        time.sleep(2)
    return {"status": "scanner_failed", "attempts": attempts, "private_log": str(log_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trivy", type=Path, default=Path(".tools/trivy/trivy"))
    parser.add_argument("--db-repository")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()
    scanner = args.trivy.resolve()
    if not scanner.is_file():
        parser.error("Supply a Trivy executable")
    if not 60 <= args.timeout_seconds <= 900:
        parser.error("Timeout must be between 60 and 900 seconds")
    root = Path(".data/trivy").resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    (root / "docker-config").mkdir(exist_ok=True, mode=0o700)
    run_dir = root / uuid.uuid4().hex[:12]
    run_dir.mkdir(mode=0o700)
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"TRIVY_USERNAME", "TRIVY_PASSWORD", "TRIVY_REGISTRY_TOKEN", "TRIVY_TOKEN"}
    }
    env["DOCKER_CONFIG"] = str(root / "docker-config")
    metadata = json.loads(Path("docs/IMAGE_METADATA_VERIFICATION.json").read_text())
    try:
        selected = runtime_images(metadata)
    except ValueError as exc:
        parser.error(str(exc))
    selected.sort(
        key=lambda row: next(
            index
            for index, name in enumerate(
                ("library/nginx", "library/python", "library/postgres", "falkordb/falkordb")
            )
            if row["image"].startswith(name)
        )
    )
    version = subprocess.check_output([str(scanner), "--version"], env=env, text=True, timeout=10)
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "scanner": version.splitlines()[0],
        "scope": "Anonymous remote scans of published runtime bases/database services only. GraphPilot-built images and container execution are not verified.",
        "images": [],
        "graphpilot_built_images_audited": False,
        "status": "incomplete",
    }
    destination = Path("docs/REMOTE_IMAGE_AUDIT.json")
    if destination.exists():
        prior = json.loads(destination.read_text())
        report["previous_attempts"] = prior.get("previous_attempts", [])[-2:] + [
            {
                "timestamp": prior["timestamp"],
                "status": prior["status"],
                "images": [
                    {k: row[k] for k in ("image", "status", "exit_code") if k in row}
                    for row in prior["images"]
                ],
            }
        ]
    try:
        for index, item in enumerate(selected):
            # Resolve the exact metadata observation rather than a mutable tag.
            image = item["image"].split("@")[0].split(":")[0] + "@" + item["digest"]
            output = run_dir / f"image-{index}.json"
            print(
                f"Auditing published image {index + 1}/{len(selected)}: {item['image']}", flush=True
            )
            command = [
                str(scanner),
                "image",
                "--image-src",
                "remote",
                "--platform",
                "linux/amd64",
                "--scanners",
                "vuln",
                "--parallel",
                "2",
                "--no-progress",
                "--timeout",
                f"{args.timeout_seconds}s",
                "--format",
                "json",
                "--output",
                str(output),
                "--cache-dir",
                str(root / "cache"),
                *(["--db-repository", args.db_repository] if args.db_repository else []),
                image,
            ]
            outcome = scan(command, output, run_dir, index, env, args.timeout_seconds)
            if outcome["status"] != "completed":
                report["images"].append({"image": image, **outcome})
                destination.write_text(json.dumps(report, indent=2) + "\n")
                continue
            data = json.loads(output.read_text())
            if (data.get("Metadata", {}).get("OS") or {}).get("Family") in {None, "", "none"}:
                report["images"].append({"image": image, "status": "os_not_identified"})
                continue
            vulnerabilities = [
                v for r in data.get("Results", []) for v in r.get("Vulnerabilities", [])
            ]
            report["images"].append(
                {
                    "image": image,
                    "status": "completed",
                    "os": data["Metadata"]["OS"],
                    "os_package_vulnerabilities_checked": True,
                    "severity_counts": dict(Counter(v["Severity"] for v in vulnerabilities)),
                    "high_critical": [
                        {
                            k: v.get(k)
                            for k in (
                                "VulnerabilityID",
                                "PkgName",
                                "InstalledVersion",
                                "FixedVersion",
                                "Severity",
                            )
                        }
                        for v in vulnerabilities
                        if v["Severity"] in {"HIGH", "CRITICAL"}
                    ],
                }
            )
            destination.write_text(json.dumps(report, indent=2) + "\n")
        if len(report["images"]) == len(selected) and all(
            x["status"] == "completed" for x in report["images"]
        ):
            report["status"] = "completed"
    finally:
        destination.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "images": [
                    {
                        "image": row["image"],
                        "status": row["status"],
                        "severity_counts": row.get("severity_counts"),
                        "high_critical_findings": len(row.get("high_critical", []))
                        if row["status"] == "completed"
                        else None,
                    }
                    for row in report["images"]
                ],
                "graphpilot_built_images_audited": False,
            },
            indent=2,
        )
    )
    if report["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
