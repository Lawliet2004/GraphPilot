"""Digest-bound publisher inventories, independent of image execution/full scans."""

import argparse
import hashlib
import json
import os
import subprocess
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx

ACCEPT = ",".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)


def fetch(client, url, headers=None):
    for attempt in range(3):
        try:
            response = client.get(url, headers=headers, follow_redirects=False)
            # Registry credentials never accompany a storage redirect.
            if response.is_redirect:
                destination = response.headers["location"]
                if not destination.startswith("https://"):
                    raise ValueError("Insecure registry storage redirect")
                response = client.get(destination, follow_redirects=True)
            if response.status_code != 200:
                raise ValueError(f"Registry HTTP {response.status_code}")
            if len(response.content) > 25_000_000:
                raise ValueError("Publisher inventory exceeds budget")
            return response.content
        except httpx.HTTPError:
            if attempt == 2:
                raise
            time.sleep(0.5)


def verified_json(client, url, digest, headers):
    raw = fetch(client, url, headers)
    if "sha256:" + hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("Registry content hash mismatch")
    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trivy", type=Path, default=Path(".tools/trivy/trivy"))
    parser.add_argument(
        "--metadata", type=Path, default=Path("docs/IMAGE_METADATA_VERIFICATION.json")
    )
    parser.add_argument("--output", type=Path, default=Path("docs/UPSTREAM_SBOM_AUDIT.json"))
    parser.add_argument(
        "--declared-distro", help="Explicit family/version for one candidate inventory"
    )
    parser.add_argument(
        "--distro-source", help="Publisher source supporting the declared distribution"
    )
    args = parser.parse_args()
    scanner = args.trivy.resolve()
    cache = Path(".data/trivy/cache").resolve()
    if not scanner.is_file() or not (cache / "db/trivy.db").is_file():
        parser.error("Supply Trivy and download its vulnerability database first")
    root = Path(".data/upstream-sboms").resolve() / uuid.uuid4().hex[:12]
    root.mkdir(parents=True, mode=0o700)
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "status": "incomplete",
        "scope": "SHA-256-bound publisher SPDX inventories for linux/amd64, analyzed with the cached vulnerability DB. No full filesystem scan, image execution or GraphPilot-built-image audit.",
        "images": [],
        "graphpilot_built_images_audited": False,
    }
    metadata = json.loads(args.metadata.read_text())
    selected = [
        r
        for r in metadata["images"]
        if r["image"].startswith(
            ("library/postgres:", "library/python:", "library/nginx:", "falkordb/falkordb@")
        )
    ]
    if args.declared_distro and (len(selected) != 1 or not args.distro_source):
        parser.error("An explicit distribution requires one image and its publisher source")
    full_scans = json.loads(Path("docs/REMOTE_IMAGE_AUDIT.json").read_text()).get("images", [])
    with httpx.Client(timeout=25) as client:
        for index, item in enumerate(selected):
            row = {
                "image": item["image"].split("@")[0].split(":")[0] + "@" + item["digest"],
                "status": "unavailable",
            }
            distro, distro_source = args.declared_distro, args.distro_source
            if not distro:
                match = next(
                    (
                        r
                        for r in full_scans
                        if r["image"] == row["image"] and r["status"] == "completed"
                    ),
                    None,
                )
                known = (match or {}).get("os") or {}
                if known.get("Family") not in {None, "", "none"}:
                    distro = known["Family"] + "/" + known["Name"]
                    distro_source = (
                        "Matching completed filesystem scan in docs/REMOTE_IMAGE_AUDIT.json"
                    )
            if distro:
                row.update(
                    os_selection=distro,
                    os_source=distro_source,
                    os_selection_kind="publisher_declaration"
                    if args.declared_distro
                    else "matching_filesystem_scan",
                )
            print("Checking publisher inventory: " + item["image"], flush=True)
            try:
                repo = item["image"].split("@")[0].split(":")[0]
                token = json.loads(
                    fetch(
                        client,
                        "https://auth.docker.io/token?service=registry.docker.io&scope=repository:"
                        + repo
                        + ":pull",
                    )
                )["token"]
                headers = {"Authorization": "Bearer " + token, "Accept": ACCEPT}
                base = "https://registry-1.docker.io/v2/" + repo
                manifest = verified_json(
                    client, base + "/manifests/" + item["digest"], item["digest"], headers
                )
                candidates = manifest.get("manifests", [])
                target = next(
                    (
                        m["digest"]
                        for m in candidates
                        if m.get("platform", {}).get("os") == "linux"
                        and m["platform"].get("architecture") == "amd64"
                    ),
                    None,
                )
                attestation = next(
                    (
                        m
                        for m in candidates
                        if m.get("annotations", {}).get("vnd.docker.reference.digest") == target
                        and target
                    ),
                    None,
                )
                if not attestation:
                    row["reason"] = "No publisher attestation for linux/amd64"
                else:
                    attached = verified_json(
                        client,
                        base + "/manifests/" + attestation["digest"],
                        attestation["digest"],
                        headers,
                    )
                    layer = next(
                        (
                            layer
                            for layer in attached.get("layers", [])
                            if layer.get("annotations", {}).get("in-toto.io/predicate-type")
                            == "https://spdx.dev/Document"
                        ),
                        None,
                    )
                    if not layer:
                        row["reason"] = "Publisher has no SPDX inventory"
                    else:
                        statement = verified_json(
                            client, base + "/blobs/" + layer["digest"], layer["digest"], headers
                        )
                        subjects = statement.get("subject", [])
                        if statement.get("predicateType") != "https://spdx.dev/Document" or not any(
                            s.get("digest", {}).get("sha256") == target.removeprefix("sha256:")
                            for s in subjects
                        ):
                            raise ValueError("Inventory subject does not match selected image")
                        sbom = statement["predicate"]
                        if not sbom.get("packages"):
                            raise ValueError("Publisher inventory is empty")
                        source, output = root / f"{index}.spdx.json", root / f"{index}.audit.json"
                        source.write_text(json.dumps(sbom))
                        os.chmod(source, 0o600)
                        log = root / f"{index}.log"
                        with log.open("wb") as stream:
                            os.chmod(log, 0o600)
                            done = subprocess.run(
                                [
                                    str(scanner),
                                    "sbom",
                                    "--skip-db-update",
                                    "--cache-backend",
                                    "memory",
                                    "--cache-dir",
                                    str(cache),
                                    "--scanners",
                                    "vuln",
                                    *(["--distro", distro] if distro else []),
                                    "--format",
                                    "json",
                                    "--output",
                                    str(output),
                                    str(source),
                                ],
                                stdout=stream,
                                stderr=stream,
                                timeout=90,
                            )
                        if done.returncode != 0:
                            raise ValueError("Inventory analyzer failed")
                        data = json.loads(output.read_text())
                        findings = [
                            v for r in data.get("Results", []) for v in r.get("Vulnerabilities", [])
                        ]
                        os_info = data.get("Metadata", {}).get("OS") or {}
                        os_identified = os_info.get("Family") not in {None, "", "none"}
                        row.update(
                            status="inventory_analyzed" if os_identified else "inventory_limited",
                            platform_manifest=target,
                            inventory_digest=layer["digest"],
                            package_count=len(sbom["packages"]),
                            os=os_info,
                            os_package_vulnerabilities_checked=os_identified,
                            severity_counts=dict(Counter(v["Severity"] for v in findings)),
                            high_critical=[
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
                                for v in findings
                                if v["Severity"] in {"HIGH", "CRITICAL"}
                            ],
                        )
            except Exception as exc:
                # Exception messages may contain signed storage URLs; retain only type.
                row.update(status="failed", error_type=type(exc).__name__)
            report["images"].append(row)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
    if all(row["status"] == "inventory_analyzed" for row in report["images"]):
        report["status"] = "inventories_analyzed"
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "images": [
                    {
                        "image": row["image"],
                        "status": row["status"],
                        "os_package_vulnerabilities_checked": row.get(
                            "os_package_vulnerabilities_checked", False
                        ),
                        "severity_counts": row.get("severity_counts"),
                    }
                    for row in report["images"]
                ],
            },
            indent=2,
        )
    )
    if report["status"] != "inventories_analyzed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
