import hashlib
import hmac
import re
import secrets
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.config import settings
from api.db import db_session, utcnow
from api.models import Audit, LoginSession, PasswordReset, User

router = APIRouter(prefix="/api/auth", tags=["authentication"])
password_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY_HASH = password_hasher.hash(secrets.token_urlsafe(32))


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def audit(db: Session, user_id: str | None, action: str, target="", **details):
    db.add(Audit(user_id=user_id, action=action, target=target, details=details))


def public_user(user: User):
    return {
        k: getattr(user, k)
        for k in ("id", "email", "name", "role", "disabled", "theme", "created_at")
    }


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def email_address(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value


class Registration(Credentials):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Name cannot be blank")
        return value.strip()


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)


def current_session(request: Request, db: Session = Depends(db_session)):
    token = request.cookies.get("gp_session", "")
    session = db.get(LoginSession, digest(token)) if token else None
    user = db.get(User, session.user_id) if session else None
    if not session or session.expires_at <= utcnow() or not user or user.disabled:
        raise HTTPException(401, "Please log in to continue")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("x-csrf-token", "")
        if not csrf or not hmac.compare_digest(session.csrf_hash, digest(csrf)):
            raise HTTPException(403, "Invalid CSRF token. Refresh the page and try again.")
    request.state.user = user
    request.state.session = session
    return user


def admin(user: User = Depends(current_session)):
    if user.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return user


def create_session(db, user, response, request):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    expires = utcnow() + timedelta(hours=settings().session_hours)
    db.add(
        LoginSession(
            id=digest(token),
            user_id=user.id,
            csrf_hash=digest(csrf),
            expires_at=expires,
            agent=request.headers.get("user-agent", "")[:200],
        )
    )
    for key, value, http_only in [("gp_session", token, True), ("gp_csrf", csrf, False)]:
        response.set_cookie(
            key,
            value,
            httponly=http_only,
            secure=settings().cookie_secure,
            samesite="lax",
            max_age=settings().session_hours * 3600,
            path="/",
        )
    return {"user": public_user(user), "csrf": csrf}


def auth_rate_limit(db, request):
    # Durable across API workers/restarts. Store a one-way IP digest, never raw addresses.
    ip = digest(request.client.host if request.client else "unknown")
    count = db.scalar(
        select(func.count())
        .select_from(Audit)
        .where(
            Audit.action == "auth.attempt",
            Audit.target == ip,
            Audit.created_at > utcnow() - timedelta(minutes=10),
        )
    )
    if count >= 30:
        raise HTTPException(429, "Too many attempts. Try again in 10 minutes.")
    audit(db, None, "auth.attempt", ip)
    db.commit()


@router.post("/register", status_code=201)
def register(
    body: Registration, request: Request, response: Response, db: Session = Depends(db_session)
):
    auth_rate_limit(db, request)
    user = User(email=body.email, name=body.name, password_hash=password_hasher.hash(body.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with that email already exists") from None
    audit(db, user.id, "account.register", user.id)
    result = create_session(db, user, response, request)
    db.commit()
    return result


@router.post("/login")
def login(body: Login, request: Request, response: Response, db: Session = Depends(db_session)):
    auth_rate_limit(db, request)
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    try:
        password_hasher.verify(user.password_hash if user else DUMMY_HASH, body.password)
    except (VerificationError, InvalidHashError):
        raise HTTPException(401, "Email or password is incorrect") from None
    if not user or user.disabled:
        raise HTTPException(401, "Email or password is incorrect")
    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = password_hasher.hash(body.password)
    # A login always rotates any previous token in this browser.
    old = request.cookies.get("gp_session")
    if old:
        db.execute(delete(LoginSession).where(LoginSession.id == digest(old)))
    result = create_session(db, user, response, request)
    audit(db, user.id, "session.login", user.id)
    db.commit()
    return result


@router.get("/session")
def me(request: Request, user: User = Depends(current_session)):
    return {"user": public_user(user), "csrf": request.cookies.get("gp_csrf", "")}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
):
    db.delete(request.state.session)
    audit(db, user.id, "session.logout", user.id)
    db.commit()
    response.delete_cookie("gp_session", path="/")
    response.delete_cookie("gp_csrf", path="/")
    return {"message": "Logged out"}


@router.get("/sessions")
def sessions(
    request: Request, user: User = Depends(current_session), db: Session = Depends(db_session)
):
    rows = db.scalars(
        select(LoginSession).where(
            LoginSession.user_id == user.id, LoginSession.expires_at > utcnow()
        )
    )
    return [
        {
            "id": s.id,
            "created_at": s.created_at,
            "expires_at": s.expires_at,
            "agent": s.agent,
            "current": s.id == request.state.session.id,
        }
        for s in rows
    ]


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: str, user: User = Depends(current_session), db: Session = Depends(db_session)
):
    session = db.get(LoginSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(404, "Session not found")
    db.delete(session)
    audit(db, user.id, "session.revoke", session_id)
    db.commit()
    return {"message": "Session revoked"}


class Profile(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    theme: str = Field(pattern="^(light|dark|system)$")


@router.patch("/profile")
def profile(
    body: Profile, user: User = Depends(current_session), db: Session = Depends(db_session)
):
    if not body.name.strip():
        raise HTTPException(422, "Name cannot be blank")
    user.name, user.theme = body.name.strip(), body.theme
    audit(db, user.id, "account.update", user.id)
    db.commit()
    return public_user(user)


class ResetRequest(BaseModel):
    email: str = Field(max_length=254)


@router.post("/password-reset")
def request_reset(body: ResetRequest, request: Request, db: Session = Depends(db_session)):
    cfg = settings()
    if not cfg.smtp_host or not cfg.smtp_from:
        raise HTTPException(
            503, "Password reset email is not configured. Contact your administrator."
        )
    auth_rate_limit(db, request)
    user = db.scalar(
        select(User).where(User.email == body.email.strip().lower(), User.disabled.is_(False))
    )
    if user:
        token = secrets.token_urlsafe(32)
        db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
        db.add(
            PasswordReset(
                id=digest(token), user_id=user.id, expires_at=utcnow() + timedelta(minutes=30)
            )
        )
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = (
            cfg.smtp_from,
            user.email,
            "Reset your GraphPilot password",
        )
        message.set_content(
            f"Reset your password within 30 minutes: {cfg.public_url}/reset-password?token={token}\nIf you did not request this, ignore this email."
        )
        try:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                if cfg.smtp_username:
                    smtp.login(cfg.smtp_username, cfg.smtp_password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException):
            db.rollback()
            raise HTTPException(503, "Email delivery is temporarily unavailable") from None
        audit(db, user.id, "account.reset_requested", user.id)
        db.commit()
    return {"message": "If the account exists, a reset email has been sent."}


class ResetPassword(BaseModel):
    token: str = Field(min_length=20, max_length=100)
    password: str = Field(min_length=12, max_length=128)


@router.post("/password-reset/confirm")
def confirm_reset(body: ResetPassword, db: Session = Depends(db_session)):
    # Consume under a lock so a token can succeed only once, including concurrent requests.
    token = db.scalar(
        select(PasswordReset).where(PasswordReset.id == digest(body.token)).with_for_update()
    )
    if not token or token.expires_at <= utcnow():
        raise HTTPException(400, "Reset link is invalid or expired")
    user = db.get(User, token.user_id)
    if not user or user.disabled:
        raise HTTPException(400, "Reset link is invalid or expired")
    user.password_hash = password_hasher.hash(body.password)
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    db.delete(token)
    audit(db, user.id, "account.password_reset", user.id)
    db.commit()
    return {"message": "Password changed. Please log in."}
