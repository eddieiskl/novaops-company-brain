from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Coroutine

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


class MCPToolError(RuntimeError):
    pass


class MCPToolClient:
    """Small production client for the NovaOps FastMCP server."""

    def __init__(self, url: str = "http://127.0.0.1:9880/mcp") -> None:
        self.url = url

    async def discover(self) -> list[dict]:
        async with streamable_http_client(self.url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await session.list_tools()
                return [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.inputSchema,
                    }
                    for tool in response.tools
                ]

    async def call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        async with streamable_http_client(self.url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments or {})
        if result.isError:
            message = " ".join(getattr(block, "text", "") for block in result.content)
            raise MCPToolError(message or f"MCP tool {name!r} failed")
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            if set(structured) == {"result"}:
                return structured["result"]
            return structured
        text = "".join(getattr(block, "text", "") for block in result.content)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def call_sync(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        return _run_blocking(self.call(name, arguments))

    def discover_sync(self) -> list[dict]:
        return _run_blocking(self.discover())


def _run_blocking(coro: Coroutine[Any, Any, Any]):
    """Run an MCP coroutine from sync code, including inside an active event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: list[Any] = []
    error: list[BaseException] = []

    def runner() -> None:
        try:
            result.append(asyncio.run(coro))
        except BaseException as exc:  # preserve the original exception and traceback type
            error.append(exc)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result[0]
