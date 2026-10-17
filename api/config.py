from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GP_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = Field("postgresql+psycopg://localhost/graphpilot", repr=False)
    origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://127.0.0.1:8000"]
    public_url: str = "http://localhost:5173"
    cookie_secure: bool = False
    session_hours: int = Field(168, ge=1, le=720)
    data_dir: Path = Path(".data")
    allowed_local_roots: list[Path] = []
    falkor_host: str = "127.0.0.1"
    falkor_port: int = 6379
    falkor_password: str | None = Field(None, repr=False)
    falkor_socket: str | None = None
    max_files: int = Field(5000, ge=1, le=50000)
    max_file_bytes: int = 1_000_000
    max_archive_bytes: int = 25_000_000
    max_extract_bytes: int = 100_000_000
    job_timeout_seconds: int = Field(300, ge=10, le=3600)
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = Field("", repr=False)
    github_token: str = Field("", repr=False)
    smtp_host: str = ""
    smtp_port: int = Field(587, ge=1, le=65535)
    smtp_username: str = Field("", repr=False)
    smtp_password: str = Field("", repr=False)
    smtp_from: str = ""
    artifact_retention_days: int = Field(30, ge=1, le=3650)
    max_log_bytes: int = Field(2_000_000, ge=1000, le=10_000_000)
    max_log_downloads: int = Field(10, ge=0, le=30)
    snapshot_retention_days: int = Field(30, ge=1, le=3650)
    snapshot_keep_per_branch: int = Field(10, ge=1, le=1000)

    @model_validator(mode="after")
    def validate_settings(self):
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("GraphPilot requires a PostgreSQL psycopg DSN")

        def origin(value):
            parsed = urlparse(value)
            try:
                port = parsed.port
            except ValueError:
                return False
            return (
                parsed.scheme in {"http", "https"}
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
                and not any((parsed.path, parsed.params, parsed.query, parsed.fragment))
                and "*" not in value
                and not any(c.isspace() for c in value)
                and (port is None or 1 <= port <= 65535)
            )

        if not self.origins or any(not origin(o) for o in self.origins):
            raise ValueError("Origins must be explicit HTTP(S) origins")
        self.public_url = self.public_url.rstrip("/")
        if not origin(self.public_url):
            raise ValueError("Public URL must be an HTTP(S) origin without a path or credentials")
        if self.environment == "production" and (
            not self.cookie_secure
            or any(not o.startswith("https://") for o in self.origins)
            or not self.public_url.startswith("https://")
            or self.public_url not in self.origins
        ):
            raise ValueError("Production requires Secure cookies and an allowed HTTPS public URL")
        if bool(self.llm_base_url) != bool(self.llm_model):
            raise ValueError("Configure both LLM base URL and model, or neither")
        if self.llm_base_url and urlparse(self.llm_base_url).scheme not in {"http", "https"}:
            raise ValueError("LLM endpoint must use HTTP(S)")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
