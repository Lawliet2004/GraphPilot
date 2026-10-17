"""Ephemeral certificates for local verification, never deployment credentials."""

import os
import subprocess
from pathlib import Path


def certificate(directory: Path, *, san="DNS:localhost,IP:127.0.0.1"):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    key, cert = directory / "key.pem", directory / "cert.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=GraphPilot local verification",
            "-addext",
            f"subjectAltName={san}",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    os.chmod(key, 0o600)
    return cert, key
