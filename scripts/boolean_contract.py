"""Read-only v2 metadata validation through the backend's pure contract reader.

No modelling libraries, MCP calls, artifact reads or approval decisions are made
here. Historical paths inside embedded ancestry remain identity labels. The gate
separately checks live payload paths against its repository boundary.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MAX_METADATA_BYTES = 24 * 1024 * 1024


def _validate(data):
    from mcp_biomodelling_servers.handoff import (
        NeKoToMaBoSSHandoffManifest, MaBoSSToPhysiCellHandoffManifest,
    )
    contracts = {
        'neko-to-maboss': NeKoToMaBoSSHandoffManifest,
        'maboss-to-physicell': MaBoSSToPhysiCellHandoffManifest,
    }
    if data.get('handoff_type') == 'neko-to-biomass':
        # Curation-bearing ODE graphs (v2.0) use the same backend contract package.
        from mcp_biomodelling_servers.ode_handoff import NeKoToBioMASSHandoffManifest
        contracts['neko-to-biomass'] = NeKoToBioMASSHandoffManifest
    contract = contracts.get(data.get('handoff_type'))
    if contract is None:
        raise ValueError('unsupported Boolean handoff type')
    try:
        return contract.model_validate(data)
    except ValueError:
        # Pydantic errors can include complete base64 snapshots. Keep those out
        # of operational error logs; the input manifest remains inspectable.
        raise ValueError('invalid v2 Boolean metadata or ancestry; inspect the manifest and verify backend v2 support') from None


def validate_metadata(data):
    """Use the current or explicitly configured Python; never install a backend."""
    encoded = json.dumps(data).encode('utf-8')
    if len(encoded) > MAX_METADATA_BYTES:
        raise ValueError('Boolean handoff metadata exceeds the 24 MiB limit')
    try:
        _validate(data)
        return
    except ImportError:
        # Claude hooks commonly start under system Python. Reuse the existing
        # workstation interpreter selection without starting the dispatcher.
        from scripts.codex.dispatcher.launch import launch_configuration
        python, environment = launch_configuration(ROOT)
    try:
        result = subprocess.run(
            [python, str(Path(__file__).resolve())], input=encoded,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=environment, cwd=ROOT, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError('v2 contract validation could not run in the configured modelling Python') from error
    if result.returncode != 0 or result.stdout != b'validated\n':
        raise ValueError('v2 contract validation failed; configure a modelling Python with the updated MCP contract package and check the manifest')


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_METADATA_BYTES + 1)
        if len(raw) > MAX_METADATA_BYTES:
            raise ValueError('Boolean handoff metadata exceeds the size limit')
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError('Boolean handoff metadata must be an object')
        _validate(data)
    except (ImportError, ValueError, TypeError, KeyError):
        print('Boolean v2 metadata validation failed; check the contract package and manifest.', file=sys.stderr)
        return 2
    print('validated')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
