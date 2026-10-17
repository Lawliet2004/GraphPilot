import os
import subprocess
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# Create a distinct real database. Never truncate a development or production DB.
base_url = make_url(
    os.getenv("GP_TEST_DATABASE_URL")
    or dotenv_values(".env").get("GP_DATABASE_URL", "postgresql+psycopg://localhost/graphpilot")
)
test_url = base_url.set(database="graphpilot_test")
os.environ["GP_DATABASE_URL"] = test_url.render_as_string(hide_password=False)
os.environ["GP_ENVIRONMENT"] = "test"
os.environ["GP_DATA_DIR"] = str(Path(".data/tests").resolve())
os.environ["GP_FALKOR_PORT"] = os.getenv(
    "GP_TEST_FALKOR_PORT", dotenv_values(".env").get("GP_FALKOR_PORT", "6379")
)
os.environ["GP_ORIGINS"] = '["http://testserver","http://localhost:5173"]'
admin_engine = create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
with admin_engine.connect() as connection:
    if not connection.scalar(text("SELECT 1 FROM pg_database WHERE datname='graphpilot_test'")):
        connection.execute(text("CREATE DATABASE graphpilot_test"))
admin_engine.dispose()
subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)

from fastapi.testclient import TestClient  # noqa: E402

from api.db import Base, SessionLocal, engine  # noqa: E402
from api.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clear_database():
    from api.services.runtime_config import clear_cache

    clear_cache()
    assert engine.url.database == "graphpilot_test"
    with engine.begin() as connection:
        tables = ",".join('"' + table.name + '"' for table in Base.metadata.sorted_tables)
        connection.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))
    yield
    clear_cache()


@pytest.fixture
def client():
    with TestClient(app, headers={"Origin": "http://testserver"}) as c:
        yield c


@pytest.fixture
def db():
    with SessionLocal() as db:
        yield db


def register(client, email="dev@example.com"):
    response = client.post(
        "/api/auth/register",
        json={"name": "Test Developer", "email": email, "password": "correct-horse-battery"},
    )
    assert response.status_code == 201, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return response.json()["user"]
