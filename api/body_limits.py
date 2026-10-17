"""Enforce request budgets before JSON/multipart parsing can spool unbounded input."""

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from api.config import settings


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = (
            settings().max_archive_bytes + 65536
            if scope["path"] == "/api/repositories/upload"
            else 65536
        )
        length = Headers(scope=scope).get("content-length")
        if length is not None:
            if not length.isdigit():
                return await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(
                    scope, receive, send
                )
            if int(length) > limit:
                return await JSONResponse(
                    {"detail": "Request exceeds the configured size limit"}, status_code=413
                )(scope, receive, send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(413, "Request exceeds the configured size limit")
            return message

        return await self.app(scope, limited_receive, send)
