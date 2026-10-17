"""Explicit administrative commands; never served as a web command-execution API."""

import argparse
import getpass
import os
from pathlib import Path

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
    promote = sub.add_parser(
        "promote-admin", help="Promote an existing account without changing credentials"
    )
    promote.add_argument("email")
    link = sub.add_parser(
        "link-firebase", help="Explicitly bind an existing account to a verified Firebase UID"
    )
    link.add_argument("email")
    link.add_argument("uid")
    issue = sub.add_parser("create-mcp-token", help="Issue a read-only token for an existing user")
    issue.add_argument("email")
    issue.add_argument("--name", default="MCP client")
    issue.add_argument("--days", type=int, default=7, choices=range(1, 31), metavar="1..30")
    issue.add_argument(
        "--output", required=True, type=Path, help="New owner-only token file; never stdout"
    )
    revoke = sub.add_parser("revoke-mcp-token", help="Revoke a token by its non-secret ID")
    revoke.add_argument("token_id")
    listing = sub.add_parser(
        "list-mcp-tokens", help="Show token IDs and expiry, never secret values"
    )
    listing.add_argument("email")
    sub.add_parser(
        "purge-artifacts", help="Delete expired archived logs; audited and safe to repeat"
    )
    prune = sub.add_parser(
        "prune-snapshots", help="Apply configured snapshot retention to an owned repository UUID"
    )
    prune.add_argument("repository_id")
    args = parser.parse_args()
    if args.command in {"promote-admin", "link-firebase"}:
        from api.services import firebase_auth

        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == args.email.strip().lower()))
            if not user or user.disabled:
                parser.error("An active existing user is required")
            if args.command == "promote-admin":
                user.role = "admin"
                audit(db, user.id, "admin.promote", user.id)
            else:
                if not firebase_auth.enabled():
                    parser.error("Configure Firebase before linking an account")
                key = firebase_auth.identity(args.uid)
                if user.firebase_identity and user.firebase_identity != key:
                    parser.error("This account is already linked to another Firebase identity")
                if db.scalar(
                    select(User.id).where(User.firebase_identity == key, User.id != user.id)
                ):
                    parser.error("This Firebase identity is already linked")
                user.firebase_identity = key
                user.password_hash = "!firebase"
                # Revoke old browser sessions and provider-independent agent tokens.
                from sqlalchemy import delete, update

                from api.db import utcnow
                from api.models import AgentToken, LoginSession

                db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
                db.execute(
                    update(AgentToken)
                    .where(AgentToken.user_id == user.id)
                    .values(revoked_at=utcnow())
                )
                audit(db, user.id, "admin.firebase_link", user.id)
            db.commit()
        print("Account permissions updated. Credentials were not printed.")
        return
    if args.command in {"create-mcp-token", "revoke-mcp-token", "list-mcp-tokens"}:
        from api.models import AgentToken
        from api.services.agent_tokens import issue_token, revoke_token

        with SessionLocal() as db:
            if args.command == "revoke-mcp-token":
                try:
                    revoke_token(db, args.token_id)
                except ValueError as exc:
                    parser.error(str(exc))
                db.commit()
                print("MCP token revoked.")
                return
            user = db.scalar(select(User).where(User.email == args.email.strip().lower()))
            if not user or user.disabled:
                parser.error("An active existing user is required")
            if args.command == "list-mcp-tokens":
                for row in db.scalars(select(AgentToken).where(AgentToken.user_id == user.id)):
                    print(
                        row.id,
                        row.name,
                        row.expires_at.isoformat(),
                        "revoked" if row.revoked_at else "",
                    )
                return
            try:
                raw, row = issue_token(db, user, args.name, args.days)
                # Refuse overwrites and symlinks; do not print bearer credentials.
                fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    with os.fdopen(fd, "w") as stream:
                        stream.write(raw + "\n")
                    db.commit()
                except BaseException:
                    args.output.unlink(missing_ok=True)
                    raise
            except (ValueError, OSError) as exc:
                parser.error(
                    f"Token not saved ({type(exc).__name__}); choose a new private file path"
                )
            print(f"Read-only MCP token saved. ID: {row.id}. Expires: {row.expires_at.isoformat()}")
        return
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
            if user.firebase_identity:
                parser.error("Firebase manages this password; use promote-admin to change its role")
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
