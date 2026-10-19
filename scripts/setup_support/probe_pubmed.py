#!/usr/bin/env python3
"""Read-only remote PubMed initialize/tools-list probe, with a process watchdog.

Use the modelling environment's Python for the worker (it provides the MCP SDK).
No searches, article retrieval, scientific sessions or repository artifacts are
created. This tests the public remote endpoint; it does not borrow desktop auth
or establish that an already running parent has a safe tool inventory.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import inspect
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.codex.launcher_config import PUBMED_TOOLS
from scripts.setup_support.configure_codex import PUBMED_URL
from scripts.setup_support.detect import run
from scripts.setup_support.state import SetupError


def endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('endpoint must be an HTTPS URL without embedded credentials, query or fragment')
    return value


async def inspect_endpoint(url, *, client_factory=None, session_factory=None, deadline_seconds=30):
    if client_factory is None or session_factory is None:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        client_factory, session_factory = streamable_http_client, ClientSession
    async with asyncio.timeout(deadline_seconds):
        async with client_factory(endpoint(url)) as streams:
            # SDK releases yield either (read, write) or (read, write, session_id).
            if not isinstance(streams, tuple) or len(streams) not in (2, 3):
                raise ValueError('unsupported MCP stream tuple')
            async with session_factory(streams[0], streams[1]) as session:
                await session.initialize()
                names, seen, cursor = [], set(), None
                for _ in range(10):
                    if cursor is None:
                        result = await session.list_tools()
                    elif 'params' in inspect.signature(session.list_tools).parameters:
                        from mcp.types import PaginatedRequestParams
                        result = await session.list_tools(params=PaginatedRequestParams(cursor=cursor))
                    else:
                        result = await session.list_tools(cursor=cursor)
                    names.extend(tool.name for tool in result.tools)
                    cursor = getattr(result, 'nextCursor', None) or getattr(result, 'next_cursor', None)
                    if not cursor:
                        return {'tools': names, 'operations': ['initialize', 'tools/list']}
                    if cursor in seen:
                        raise ValueError('repeated tool-list cursor')
                    seen.add(cursor)
                raise ValueError('too many tool-list pages')


def probe(python: str, *, url: str = PUBMED_URL, timeout: float = 40) -> dict:
    """Bound network RPCs AND SDK cleanup with an external process deadline."""
    endpoint(url)
    if not 0 < timeout <= 60:
        raise ValueError('probe timeout must be greater than zero and at most 60 seconds')
    try:
        completed = run([python, str(Path(__file__).resolve()), '--worker', '--url', url], timeout=timeout)
        data = json.loads(completed.stdout)
        names = data.get('tools')
        if not isinstance(names, list) or any(not isinstance(name, str) for name in names) or len(set(names)) != len(names):
            raise ValueError('invalid tool inventory')
        missing = sorted(set(PUBMED_TOOLS) - set(names))
        if missing:
            return {'passed': False, 'error': 'required PubMed capabilities unavailable', 'missing_tools': missing, 'scientific_calls': 0}
        return {'passed': True, 'backend': 'pubmed', 'tool_count': len(names), 'required_tools': list(PUBMED_TOOLS),
                'operations': ['initialize', 'tools/list'], 'scientific_calls': 0, 'desktop_auth_used': False}
    except (SetupError, ValueError, TypeError, AttributeError):
        # Transport exceptions can contain URLs, headers or server messages.
        # Return only a fixed, actionable failure; never reflect raw stderr.
        return {'passed': False, 'error': 'PubMed connectivity probe failed or exceeded its process deadline; verify network access and endpoint authentication',
                'scientific_calls': 0, 'desktop_auth_used': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=sys.executable, help='Python with MCP SDK installed')
    parser.add_argument('--url', default=PUBMED_URL)
    parser.add_argument('--timeout', type=float, default=40)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.worker:
            result = asyncio.run(inspect_endpoint(args.url))
        else:
            result = probe(args.python, url=args.url, timeout=args.timeout)
        print(json.dumps(result, indent=2))
        return 0 if args.worker or result['passed'] else 2
    except Exception:
        print(json.dumps({'passed': False, 'error': 'PubMed probe configuration or transport failed'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
