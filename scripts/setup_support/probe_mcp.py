"""Run with the modelling Python: MCP initialize/list_tools only, never call_tool."""
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import PaginatedRequestParams


async def probe():
    async with stdio_client(StdioServerParameters(command=sys.argv[1], env=dict(os.environ))) as (read, write):
        async with ClientSession(read, write) as session:
            async with asyncio.timeout(30):
                await session.initialize()
            names = []
            cursor = None
            seen = set()
            while True:
                async with asyncio.timeout(30):
                    result = await session.list_tools(params=PaginatedRequestParams(cursor=cursor))
                names.extend(tool.name for tool in result.tools)
                cursor = result.next_cursor
                if not cursor:
                    break
                if cursor in seen:
                    raise RuntimeError("Repeated tool-list cursor")
                seen.add(cursor)
            print(json.dumps({"tools": names}))


async def main(*, deadline_seconds: float = 60):
    # Bound the whole paginated probe, not only individual RPCs. Cancelling
    # inside these SDK contexts gives stdio_client time to reap its detached
    # server before the outer 90-second watchdog is needed.
    async with asyncio.timeout(deadline_seconds):
        await probe()


if __name__ == "__main__":
    asyncio.run(main())
