"""Explicit administrative commands; never served as a web command-execution API."""

import argparse
import getpass

from sqlalchemy import select

from api.auth import Credentials, audit, password_hasher
from api.db import SessionLocal
from api.models import User


def main():
    parser = argparse.ArgumentParser(prog="graphpilot")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-admin", help="Bootstrap or promote an administrator")
    create.add_argument("email")
    create.add_argument("--name", default="Administrator")
    sub.add_parser(
        "purge-artifacts", help="Delete expired archived logs; audited and safe to repeat"
    )
    prune = sub.add_parser(
        "prune-snapshots", help="Apply configured snapshot retention to an owned repository UUID"
    )
    prune.add_argument("repository_id")
    args = parser.parse_args()
    if args.command == "prune-snapshots":
        from api.services.lifecycle import prune_snapshots

        print(prune_snapshots(args.repository_id))
        return
    if args.command == "purge-artifacts":
        from api.services.artifacts import purge_expired_logs

        print(purge_expired_logs())
        return
    password = getpass.getpass("Password (12+ characters): ")
    if password != getpass.getpass("Confirm password: "):
        parser.error("Passwords do not match")
    validated = Credentials(email=args.email, password=password)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == validated.email))
        if user:
            user.role = "admin"
            user.disabled = False
            user.password_hash = password_hasher.hash(password)
        else:
            user = User(
                email=validated.email,
                name=args.name,
                role="admin",
                password_hash=password_hasher.hash(password),
            )
            db.add(user)
            db.flush()
        audit(db, user.id, "admin.bootstrap", user.id)
        db.commit()
    print("Administrator account ready. Log in through the application.")


if __name__ == "__main__":
    main()
