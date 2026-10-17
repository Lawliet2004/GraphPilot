from collections.abc import Generator
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from api.config import settings


class Base(DeclarativeBase):
    pass


def utcnow():
    return datetime.now(UTC)


engine = create_engine(settings().database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def db_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
