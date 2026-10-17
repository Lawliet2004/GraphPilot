"""Read-only real SDK + stdio bridge verification using an operator-issued token."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from api.mcp_bridge import connection_settings


async def exercise(session, repository_id=None, query=None):
    await session.initialize()
    tools = (await session.list_tools()).tools
    expected = {
        "list_repositories",
        "search_symbols",
        "read_evidence",
        "inspect_impact",
        "indexing_status",
    }
    assert {tool.name for tool in tools} == expected
    assert all(tool.annotations and tool.annotations.readOnlyHint for tool in tools)
    result = await session.call_tool("list_repositories", {})
    assert not result.isError
    assert result.structuredContent is not None, "Structured MCP results missing"
    repos = result.structuredContent["repositories"]
    report = {
        "tool_count": len(tools),
        "accessible_repository_count": len(repos),
        "read_only": True,
    }
    if repository_id and query:
        found = await session.call_tool(
            "search_symbols", {"repository_id": repository_id, "query": query}
        )
        assert not found.isError and found.structuredContent["results"]
        node = found.structuredContent["results"][0]
        evidence = await session.call_tool(
            "read_evidence", {"repository_id": repository_id, "node_id": node["id"]}
        )
        assert not evidence.isError and evidence.structuredContent["content"]
        status = await session.call_tool("indexing_status", {"repository_id": repository_id})
        assert not status.isError
        report.update(symbol_search=True, nonempty_source_evidence=True, indexing_status=True)
    return report


async def verify(repository_id=None, query=None):
    url, token = connection_settings()
    async with httpx.AsyncClient(
        headers={"Authorization": "Bearer " + token},
        timeout=45,
        follow_redirects=False,
        trust_env=False,
    ) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                direct = await exercise(session, repository_id, query)
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "api.mcp_bridge"], env=dict(os.environ)
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            bridge = await exercise(session, repository_id, query)
    return {
        "status": "passed",
        "direct_streamable_http": direct,
        "stdio_bridge": bridge,
        "scope": "Real MCP SDK discovery and read-only tool calls; no OAuth/client installation claim",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-id")
    parser.add_argument("--query")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not __debug__:
        parser.error("Verification requires assertions")
    try:
        report = asyncio.run(verify(args.repository_id, args.query))
    except Exception as exc:
        report = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "notice": "Inspect endpoint, token, permissions and index readiness privately.",
        }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
