"""Smoke-test a Streamable HTTP MCP endpoint.

Usage:
    python scripts/test_mcp_client.py http://127.0.0.1:8000/mcp
    python scripts/test_mcp_client.py https://your-ngrok-domain.ngrok-free.app/mcp
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


DEFAULT_URL = "http://127.0.0.1:8000/mcp"
OVERVIEW_TOOL = "power_get_system_overview"


def _content_to_text(content: list[Any]) -> str:
    parts: list[str] = []
    for item in content:
        text = getattr(item, "text", None)
        if text is not None:
            parts.append(text)
            continue
        parts.append(str(item))
    return "\n".join(parts)


async def test_mcp_endpoint(url: str) -> int:
    print(f"Connecting MCP endpoint: {url}")
    async with streamablehttp_client(url) as (read_stream, write_stream, get_session_id):
        async with ClientSession(read_stream, write_stream) as session:
            init = await session.initialize()
            print(f"Initialized: {init.serverInfo.name} {init.serverInfo.version}")

            tools = await session.list_tools()
            tool_names = [tool.name for tool in tools.tools]
            print(f"Tools ({len(tool_names)}): {', '.join(tool_names)}")

            if OVERVIEW_TOOL not in tool_names:
                print(f"ERROR: required tool not found: {OVERVIEW_TOOL}")
                return 2

            result = await session.call_tool(
                OVERVIEW_TOOL,
                {"params": {"response_format": "json"}},
            )
            if result.isError:
                print("ERROR: tool call returned isError=true")
                print(_content_to_text(result.content))
                return 3

            text = _content_to_text(result.content)
            print("Tool call succeeded.")
            try:
                data = json.loads(text)
                print(
                    json.dumps(
                        {
                            "database_ready": data.get("project", {}).get("database_ready"),
                            "records": data.get("counts", {}).get("inspection_records"),
                            "alerts": data.get("counts", {}).get("alerts"),
                            "latest_status": (
                                data.get("current", {}).get("latest_record") or {}
                            ).get("overall_status"),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            except json.JSONDecodeError:
                print(text[:1000])

            session_id = get_session_id()
            if session_id:
                print(f"Session ID: {session_id}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Test a Streamable HTTP MCP endpoint.")
    parser.add_argument("url", nargs="?", default=DEFAULT_URL, help=f"MCP URL, default: {DEFAULT_URL}")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(test_mcp_endpoint(args.url)))


if __name__ == "__main__":
    main()
