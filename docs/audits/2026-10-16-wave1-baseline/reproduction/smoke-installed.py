"""Initialize/list installed stdio servers; never call a modelling tool."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parent
EXPECTED = '2.4.0+wave1.20261016'

async def check(name, artifact_root):
    environment = os.environ.copy()
    environment.update(PYTHONPATH=str(ROOT / 'offline-startup'), MPLBACKEND='Agg',
                       MCP_BIOMODELLING_ARTIFACT_ROOT=str(artifact_root))
    executable = Path(sys.executable).parent / f'mcp-{name.lower()}-server'
    with (ROOT / 'logs' / f'{name}-startup.stderr.log').open('w') as log:
        transport = stdio_client(StdioServerParameters(command=str(executable), env=environment,
                                 cwd=str(ROOT)), errlog=log)
        async with Client(transport, read_timeout_seconds=30) as client:
            listing = await client.list_tools()
            assert client.server_info.name == name
            assert client.server_info.version == EXPECTED
            assert listing.tools
            return {'server': name, 'version': client.server_info.version,
                    'tool_count': len(listing.tools), 'command': str(executable),
                    'modelling_tool_calls': 0}

async def main():
    results = []
    with tempfile.TemporaryDirectory(prefix='startup-', dir=ROOT) as temporary:
        artifact_root = Path(temporary)
        for name in ('NeKo', 'MaBoSS', 'PhysiCell', 'BioMASS'):
            results.append(await asyncio.wait_for(check(name, artifact_root), timeout=45))
        assert not list(artifact_root.rglob('session_meta.json')), 'Startup created a scientific session'
    print(json.dumps({'passed': True, 'servers': results}, indent=2))

asyncio.run(main())
