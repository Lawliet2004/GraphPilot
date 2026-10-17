import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from api.auth import current_session
from api.auth import router as auth_router
from api.body_limits import BodyLimitMiddleware
from api.config import settings
from api.db import engine
from api.graph.store import client
from api.mcp_server import create_server, mcp_app
from api.services.telemetry import record_request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
# Provider URLs can contain short-lived signed credentials. Keep transport URL
# logging out of application logs; our own events never include query strings.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("graphpilot")


@asynccontextmanager
async def lifespan(app):
    settings().data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    log.info("event=application_start environment=%s", settings().environment)
    mcp = create_server()
    mcp_app.app = mcp.streamable_http_app()
    async with mcp.session_manager.run():
        yield
    engine.dispose()
    log.info("event=application_stop")


app = FastAPI(
    title="GraphPilot",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if settings().environment == "production" else "/api/docs",
    redoc_url=None if settings().environment == "production" else "/api/redoc",
    openapi_url=None if settings().environment == "production" else "/api/openapi.json",
)
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings().origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token", "Authorization", "MCP-Protocol-Version"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    request_id = str(uuid.uuid4())
    started = time.perf_counter()
    request.state.started = started
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and request.headers.get("origin") not in settings().origins
        and not (request.url.path.startswith("/api/mcp/") and not request.headers.get("origin"))
    ):
        response = JSONResponse({"detail": "Request origin is not allowed"}, status_code=403)
    else:
        try:
            response = await call_next(request)
        except Exception as exc:
            # Do not let server traceback logging expose untrusted exception text.
            response = await unexpected_error(request, exc)
    response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
            "X-Request-ID": request_id,
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        }
    )
    if settings().cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    record_request(response.status_code, elapsed)
    response.headers["Server-Timing"] = f"api;dur={elapsed}"
    # Query strings and bodies may contain sensitive text; never log them.
    log.info(
        "event=http_request method=%s status=%s duration_ms=%s request_id=%s",
        request.method,
        response.status_code,
        elapsed,
        request_id,
    )
    return response


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    log.error("event=application_error error_type=%s", type(exc).__name__)
    return JSONResponse(
        {"detail": "The operation failed. Please retry or contact your administrator."},
        status_code=500,
    )


@app.get("/api/health/live")
def live():
    return {"status": "alive"}


@app.get("/api/health/ready")
def ready():
    checks = {}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["postgresql"] = "connected"
    except Exception:
        checks["postgresql"] = "unavailable"
    try:
        client().connection.ping()
        checks["falkordb"] = "connected"
    except Exception:
        checks["falkordb"] = "unavailable"
    ok = all(v == "connected" for v in checks.values())
    return JSONResponse(
        {"status": "ready" if ok else "unavailable", "checks": checks},
        status_code=200 if ok else 503,
    )


@app.get("/api/capabilities")
def capabilities(user=Depends(current_session)):
    cfg = settings()
    return {
        "python_semantic_indexing": True,
        "other_languages": "file references only",
        "local_sources": bool(cfg.allowed_local_roots),
        "archive_upload": True,
        "llm_configured": bool(cfg.llm_base_url and cfg.llm_model),
        "github_authenticated": bool(cfg.github_token),
        "password_reset_email": bool(cfg.smtp_host and cfg.smtp_from),
    }


app.include_router(auth_router)

from api.routes.repositories import router as repository_router  # noqa: E402

app.include_router(repository_router)

from api.routes.admin import router as admin_router  # noqa: E402
from api.routes.context import router as context_router  # noqa: E402

app.include_router(admin_router)
app.include_router(context_router)

# A separate bearer gate protects every MCP request; browser cookie sessions are
# never accepted here. The trailing slash is part of the client endpoint.
app.mount("/api/mcp", mcp_app)
