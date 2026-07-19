"""Smoke-test the power monitoring MCP Streamable HTTP endpoint.

Examples:
    python scripts/test_mcp_client.py
    python scripts/test_mcp_client.py --url http://127.0.0.1:8000/mcp
    python scripts/test_mcp_client.py --url https://example.ngrok-free.dev/mcp
    python scripts/test_mcp_client.py --url http://127.0.0.1:8000/mcp --host-header example.ngrok-free.dev
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import traceback
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


DEFAULT_URL = "http://127.0.0.1:8000/mcp"
DEFAULT_TOOL = "power_get_runtime_diagnostics"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test the power monitoring MCP endpoint.")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"MCP endpoint URL. Default: {DEFAULT_URL}")
    parser.add_argument(
        "--host-header",
        default=None,
        help="Optional Host header override, useful for reproducing reverse-proxy/ngrok Host errors.",
    )
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP connect/write timeout in seconds.")
    parser.add_argument("--sse-timeout", type=float, default=30.0, help="SSE read timeout in seconds.")
    parser.add_argument(
        "--skip-tool-call",
        action="store_true",
        help=f"Only initialize and list tools; do not call {DEFAULT_TOOL}.",
    )
    parser.add_argument("--tool", default=DEFAULT_TOOL, help=f"Tool to call after listing tools. Default: {DEFAULT_TOOL}")
    parser.add_argument(
        "--arguments",
        default='{"params":{"response_format":"json"}}',
        help="JSON object passed as tool arguments.",
    )
    parser.add_argument("--traceback", action="store_true", help="Print the full Python traceback on failure.")
    return parser.parse_args()


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    return value


def content_preview(value: Any) -> str:
    data = to_jsonable(value)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) > 1200:
        return text[:1200] + "\n... <truncated>"
    return text


def format_exception_tree(exc: BaseException, indent: int = 0) -> str:
    prefix = "  " * indent
    lines = [f"{prefix}{type(exc).__name__}: {exc}"]
    if isinstance(exc, BaseExceptionGroup):
        for index, child in enumerate(exc.exceptions, start=1):
            lines.append(f"{prefix}sub-exception {index}:")
            lines.append(format_exception_tree(child, indent + 1))
    elif exc.__cause__ is not None:
        lines.append(f"{prefix}caused by:")
        lines.append(format_exception_tree(exc.__cause__, indent + 1))
    elif exc.__context__ is not None:
        lines.append(f"{prefix}context:")
        lines.append(format_exception_tree(exc.__context__, indent + 1))
    return "\n".join(lines)


async def run_client(args: argparse.Namespace) -> None:
    headers = {}
    if args.host_header:
        headers["Host"] = args.host_header

    print(f"[connect] url={args.url}")
    if headers:
        print(f"[connect] extra_headers={headers}")

    async with streamablehttp_client(
        args.url,
        headers=headers or None,
        timeout=args.timeout,
        sse_read_timeout=args.sse_timeout,
    ) as (read_stream, write_stream, get_session_id):
        async with ClientSession(read_stream, write_stream) as session:
            init_result = await session.initialize()
            print("[initialize] ok")
            print(f"[initialize] protocol={init_result.protocolVersion}")
            print(f"[initialize] session_id={get_session_id()}")

            tools_result = await session.list_tools()
            tool_names = [tool.name for tool in tools_result.tools]
            print(f"[tools/list] count={len(tool_names)}")
            for name in tool_names:
                print(f"  - {name}")

            if args.skip_tool_call:
                return

            if args.tool not in tool_names:
                print(f"[call/tool] skipped: {args.tool} not found")
                return

            tool_arguments = json.loads(args.arguments)
            result = await session.call_tool(args.tool, tool_arguments)
            print(f"[call/tool] {args.tool} ok")
            print(content_preview(result.content))


def main() -> int:
    args = parse_args()
    try:
        asyncio.run(run_client(args))
        return 0
    except Exception as exc:
        error_text = format_exception_tree(exc)
        print("[error]", file=sys.stderr)
        print(error_text, file=sys.stderr)
        if "Invalid Host header" in error_text or "421 Misdirected Request" in error_text:
            print(
                "[hint] The MCP server rejected the HTTP Host header. "
                "Use 127.0.0.1/localhost, or add the proxy domain to POWER_MCP_ALLOWED_HOSTS.",
                file=sys.stderr,
            )
        if args.traceback:
            traceback.print_exception(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
