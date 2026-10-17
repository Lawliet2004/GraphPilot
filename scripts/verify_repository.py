"""Scan only Git candidate files; never read ignored credentials or private data."""

import argparse
import json
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gitleaks",
        type=Path,
        default=Path(
            shutil.which("gitleaks") or ".tools/gitleaks-download/extracted/usr/bin/gitleaks"
        ),
    )
    args = parser.parse_args()
    if not __debug__:
        parser.error("Verification requires assertions; run Python without -O")
    scanner = args.gitleaks.resolve()
    if not scanner.is_file():
        parser.error("Install Gitleaks or supply --gitleaks /path/to/gitleaks")
    files = [
        Path(x.decode())
        for x in subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
        ).split(b"\0")
        if x
    ]
    probes = [
        ".env",
        ".env.production",
        "app/.env.local",
        ".data/private.dump",
        ".tools/binary",
        "backups/postgres.dump",
        "app/dist/index.html",
        "node_modules/fixture.js",
    ]
    ignored = {}
    for path in probes:
        ignored[path] = subprocess.run(["git", "check-ignore", "--quiet", path]).returncode == 0
    assert all(ignored.values()), "A private/generated path is not ignored"
    for path in files:
        assert path.is_file() and not path.is_symlink(), "Unexpected nonregular Git candidate"
        assert not any(
            part in {".data", ".tools", "node_modules", "backups", "__pycache__"}
            for part in path.parts
        ), "Private/generated file is a Git candidate"
        assert path.name == ".env.example" or not path.name.startswith(".env"), (
            "Credential file is a Git candidate"
        )
    with tempfile.TemporaryDirectory(prefix="graphpilot-candidates-") as directory:
        snapshot = Path(directory)
        for path in files:
            target = snapshot / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        report_path = snapshot / "scanner.json"
        completed = subprocess.run(
            [
                str(scanner),
                "detect",
                "--no-git",
                "--source",
                str(snapshot),
                "--config",
                str(snapshot / ".gitleaks.toml"),
                "--redact",
                "--no-banner",
                "--report-format",
                "json",
                "--report-path",
                str(report_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert completed.returncode in {0, 1}, "Secret scanner failed; scan is not a success"
        findings = json.loads(report_path.read_text())
        report = {
            "timestamp": datetime.now(UTC).isoformat(),
            "candidate_files": len(files),
            "scope": "Current Git candidates only; no history/remote or guarantee of secret absence",
            "scanner": "Gitleaks; default rules extended only for two exact invalid redaction fixtures",
            "ignored_probes": ignored,
            "findings": [
                {
                    "file": str(Path(f["File"]).relative_to(snapshot)),
                    "line": f["StartLine"],
                    "rule": f["RuleID"],
                }
                for f in findings
            ],
            "status": "passed" if completed.returncode == 0 and not findings else "failed",
        }
    Path("docs/REPOSITORY_VERIFICATION.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
