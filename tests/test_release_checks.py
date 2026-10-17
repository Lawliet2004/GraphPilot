"""Release gates must reject missing evidence as well as known vulnerabilities."""

import copy
import json
import subprocess
from pathlib import Path

import pytest

from scripts.audit_container_images import SERVICES, assess, audit, public_report, verified_images
from scripts.audit_remote_images import runtime_images

APP = "sha256:" + "a" * 64
SERVICE = "sha256:" + "b" * 64


def verification():
    return {
        "status": "passed",
        "runtime_executed": True,
        "images_built_and_services_ready": True,
        "service_images": {
            s: APP if s in {"api", "worker", "migrate"} else SERVICE for s in SERVICES
        },
        "container_images": [APP, SERVICE],
    }


def scan(image=APP):
    return {
        "SchemaVersion": 2,
        "Metadata": {
            "ImageID": image,
            "OS": {"Family": "alpine", "Name": "3.24"},
            "ImageConfig": {"config": {"Env": ["PRIVATE=fixture-only"]}},
        },
        "Results": [
            {"Class": "os-pkgs", "Type": "alpine", "Packages": [{"Name": "musl"}]},
            {
                "Class": "lang-pkgs",
                "Type": "python-pkg",
                "Packages": [
                    {"Name": name} for name in ("fastapi", "SQLAlchemy", "falkordb", "psycopg")
                ],
            },
        ],
    }


@pytest.mark.parametrize(
    "change",
    [
        {"status": "configuration_only"},
        {"runtime_executed": False},
        {"runtime_executed": 1},
        {"images_built_and_services_ready": False},
        {"container_images": []},
        {"container_images": [APP]},
        {"service_images": {}},
        {"service_images": {s: "mutable:latest" for s in SERVICES}},
        {"service_images": {s: APP for s in SERVICES - {"worker"}}},
    ],
)
def test_image_gate_rejects_incomplete_runtime_evidence(change):
    with pytest.raises(ValueError):
        verified_images(verification() | change)


def test_image_gate_deduplicates_complete_service_coverage():
    assert verified_images(verification()) == [APP, SERVICE]


@pytest.mark.parametrize(
    "defect",
    [
        "wrong-image",
        "unknown-os",
        "missing-os-packages",
        "missing-python",
        "missing-app-dependency",
        "suppressed",
        "unknown-severity",
    ],
)
def test_image_gate_rejects_incomplete_or_modified_scan(defect):
    data = scan()
    if defect == "wrong-image":
        data["Metadata"]["ImageID"] = SERVICE
    elif defect == "unknown-os":
        data["Metadata"]["OS"]["Family"] = "none"
    elif defect == "missing-os-packages":
        data["Results"][0]["Packages"] = []
    elif defect == "missing-python":
        data["Results"].pop()
    elif defect == "missing-app-dependency":
        data["Results"][1]["Packages"].pop()
    elif defect == "suppressed":
        data["Results"][0]["ExperimentalModifiedFindings"] = [{"Status": "not_affected"}]
    else:
        data["Results"][0]["Vulnerabilities"] = [{"Severity": "unrecognized"}]
    with pytest.raises(ValueError):
        assess(data, APP, require_python=True)


@pytest.mark.parametrize(
    "severity,status", [("MEDIUM", "passed"), ("HIGH", "findings"), ("CRITICAL", "findings")]
)
def test_image_gate_counts_findings_without_a_fix(severity, status):
    data = scan()
    data["Results"][0]["Vulnerabilities"] = [{"Severity": severity, "FixedVersion": ""}]
    result = assess(data, APP, require_python=True)
    assert result["status"] == status
    assert result["severity_counts"] == {severity: 1}


def test_image_gate_rejects_end_of_life_even_without_findings():
    data = scan()
    data["Metadata"]["OS"]["EOSL"] = True
    assert assess(data, APP)["status"] == "end_of_life"


def test_public_image_report_excludes_configuration_environment():
    sanitized = public_report(scan())
    assert "PRIVATE" not in json.dumps(sanitized)
    assert assess(sanitized, APP, require_python=True)["status"] == "passed"


@pytest.mark.parametrize(
    "first_outcome", ["error", "timeout", "invalid-json", "wrong-image", "findings", "passed"]
)
def test_audit_continues_after_failure_and_records_every_image(
    tmp_path, monkeypatch, first_outcome
):
    monkeypatch.setenv("TRIVY_SKIP_FILES", "*")
    calls = []

    def fake_scan(command, **kwargs):
        assert "TRIVY_SKIP_FILES" not in kwargs["env"]
        assert command[command.index("--config") + 1] == ""
        assert command[command.index("--ignorefile") + 1] == ""
        assert "--ignore-unfixed=false" in command
        image = command[-1]
        calls.append(image)
        raw = Path(command[command.index("--output") + 1])
        if image == APP and first_outcome == "error":
            return subprocess.CompletedProcess(command, 2)
        if image == APP and first_outcome == "timeout":
            raise subprocess.TimeoutExpired(command, 615)
        data = scan(image)
        if image == APP and first_outcome == "findings":
            data["Results"][0]["Vulnerabilities"] = [{"Severity": "HIGH"}]
        if image == APP and first_outcome == "wrong-image":
            data["Metadata"]["ImageID"] = SERVICE
        raw.write_text(
            "invalid json" if image == APP and first_outcome == "invalid-json" else json.dumps(data)
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_scan)
    output = tmp_path / "summary.json"
    report = audit(verification(), output, Path("/synthetic-trivy"))
    assert calls == [APP, SERVICE]
    assert report["images"][1]["status"] == "passed"
    assert report["status"] == ("passed" if first_outcome == "passed" else "failed")
    assert json.loads(output.read_text()) == report
    for result in tmp_path.glob("run-*/*.json"):
        assert "PRIVATE" not in result.read_text()


def test_audit_refuses_empty_input_before_starting_a_scanner(tmp_path, monkeypatch):
    def refuse_scan(*args, **kwargs):
        pytest.fail("Invalid evidence must not invoke a scanner")

    monkeypatch.setattr(subprocess, "run", refuse_scan)
    before = copy.deepcopy({})
    report = audit(before, tmp_path / "summary.json", Path("/synthetic-trivy"))
    assert report["status"] == "invalid_verification"
    assert report["images"] == []


def test_upstream_audits_cover_server_variant_and_reject_empty_selection():
    server = {"image": "falkordb/falkordb-server:v4.22.1-alpine"}
    metadata = {"images": [server, {"image": "library/nginx-unrelated:latest"}]}
    assert runtime_images(metadata) == [server]
    for images in ([], [{"image": "library/node:22"}]):
        with pytest.raises(ValueError):
            runtime_images({"images": images})
