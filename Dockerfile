FROM ghcr.io/astral-sh/uv:0.13.1 AS uv
FROM python:3.12-alpine3.24@sha256:1b668429b3511ab407d8e00648891631b0b1a4d7e15e3ca70f38ab5b91ad4ab4 AS build
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-alpine3.24@sha256:1b668429b3511ab407d8e00648891631b0b1a4d7e15e3ca70f38ab5b91ad4ab4 AS runtime
RUN apk add --no-cache --upgrade git ca-certificates 'zlib>=1.3.2-r1' \
    && python -m pip uninstall -y pip \
    && rm -rf /usr/local/lib/python3.12/ensurepip \
    && addgroup -g 10001 graphpilot \
    && adduser -D -u 10001 -G graphpilot graphpilot
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
