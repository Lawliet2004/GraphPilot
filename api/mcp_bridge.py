"""Portable stdio bridge to GraphPilot's authenticated cloud MCP endpoint.

Only this file is imported locally; database credentials are not needed.
"""

import asyncio
import logging
import os
import stat
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent


def connection_settings():
    url = os.environ.get("GP_MCP_URL", "")
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path != "/api/mcp/"
        or parsed.scheme == "http"
        and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
    ):
        raise ValueError("Set GP_MCP_URL to the HTTPS /api/mcp/ endpoint")
    path = Path(os.environ["GP_MCP_TOKEN_FILE"])
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("Use a regular owner-only token file (chmod 600)")
    raw = path.read_text().strip()
    if not raw.startswith("gp_mcp_") or len(raw) > 128:
        raise ValueError("Invalid token file")
    return url, raw


async def main():
    url, token = connection_settings()
    # No bearer values or signed URLs are logged. Redirects are deliberately off.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("mcp").setLevel(logging.WARNING)
    async with httpx.AsyncClient(
        headers={"Authorization": "Bearer " + token},
        timeout=45,
        follow_redirects=False,
        trust_env=False,
    ) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as remote:
                await remote.initialize()
                server = Server("graphpilot-bridge")

                @server.list_tools()
                async def tools():
                    return (await remote.list_tools()).tools

                @server.call_tool()
                async def call(name, arguments):
                    try:
                        return await remote.call_tool(name, arguments)
                    except Exception:
                        return CallToolResult(
                            isError=True,
                            content=[
                                TextContent(
                                    type="text",
                                    text="GraphPilot connection unavailable. Check the endpoint and token.",
                                )
                            ],
                        )

                async with stdio_server() as (incoming, outgoing):
                    await server.run(incoming, outgoing, server.create_initialization_options())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(
            f"GraphPilot MCP bridge could not connect ({type(exc).__name__}). "
            "Check GP_MCP_URL, GP_MCP_TOKEN_FILE and server availability.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
