"""The developer CLI works from another checkout without importing its code."""

import subprocess
from pathlib import Path


def test_launcher_works_outside_graphpilot_and_preserves_caller_directory(tmp_path):
    root = Path(__file__).resolve().parents[1]
    checkout = tmp_path / "another checkout"
    checkout.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(checkout)], check=True)
    shadow = tmp_path / "api"
    shadow.mkdir()
    marker = tmp_path / "unexpected-import"
    (shadow / "__init__.py").write_text(
        "from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n"
    )
    (shadow / "client.py").write_text("raise RuntimeError('wrong module')\n")
    completed = subprocess.run(
        [str(root / "scripts/graphpilot"), "git", "daily", "--path", "another checkout"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert "branch: main" in completed.stdout
    assert "status: clean" in completed.stdout
    assert not marker.exists()
