"""Remove only generated disposable E2E data from this development application."""

import re
import shutil
from pathlib import Path

from sqlalchemy import delete, select

from api.config import settings
from api.db import SessionLocal
from api.graph import store
from api.models import Repository, User

pattern = re.compile(r"^e2e-(?:(?:admin|member)-)?[a-f0-9-]{36}@graphpilot\.invalid$")
root = settings().data_dir.resolve()
with SessionLocal() as db:
    users = [u for u in db.scalars(select(User)) if pattern.fullmatch(u.email)]
    ids = [u.id for u in users]
    repos = list(db.scalars(select(Repository).where(Repository.owner_id.in_(ids)))) if ids else []
    for repo in repos:
        prefix = "gp_" + repo.id.replace("-", "") + "_"
        for name in store.client().list_graphs():
            if name.startswith(prefix):
                store.delete_graph(name)
        shutil.rmtree(root / "snapshots" / repo.id, ignore_errors=True)
        if repo.source_type == "archive":
            archive = Path(repo.source).resolve()
            if archive.is_relative_to(root / "uploads"):
                archive.unlink(missing_ok=True)
        db.delete(repo)
    db.flush()
    if ids:
        db.execute(delete(User).where(User.id.in_(ids)))
    db.commit()
    print(
        f"Removed {len(users)} generated test accounts and {len(repos)} test repositories; audit events retained."
    )
