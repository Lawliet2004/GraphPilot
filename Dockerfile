FROM ghcr.io/astral-sh/uv:0.13.1 AS uv
FROM python:3.12-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS build
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/* && useradd -m -u 10001 graphpilot
WORKDIR /app
COPY --from=build --chown=graphpilot:graphpilot /app/.venv /app/.venv
COPY --chown=graphpilot:graphpilot api ./api
COPY --chown=graphpilot:graphpilot migrations ./migrations
COPY --chown=graphpilot:graphpilot alembic.ini ./
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 GP_DATA_DIR=/data
RUN mkdir /data && chown graphpilot:graphpilot /data
USER graphpilot
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips=*"]
