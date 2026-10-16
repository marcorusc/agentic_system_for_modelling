"""Run the combined identifier/reference baseline tests without provider access."""
import os
import socket
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
checkout = root / 'checkouts/Neko'
os.chdir(checkout)
sys.path.insert(0, str(checkout))

def denied(*args, **kwargs):
    raise OSError('External provider access disabled for offline baseline tests')

socket.getaddrinfo = denied
socket.create_connection = denied
socket.socket.connect = denied
socket.socket.connect_ex = denied
import requests
requests.sessions.Session.request = denied

import neko
assert Path(neko.__file__).resolve().is_relative_to(checkout)
print('Tested NeKo source:', neko.__file__, flush=True)
import pytest
raise SystemExit(pytest.main([
    '-q', '--tb=short', 'tests/test_sif_identifiers.py', 'tests/test_sif_references.py',
    'tests/test_identifier_mapping.py', 'tests/test_core.py',
    'tests/test_modify_node_name.py', 'tests/test_chebi_mapping.py',
    'tests/test_network.py::test_aliases_share_one_canonical_visualizer_node',
    'tests/test_network.py::test_gene_symbol_conversion_prefers_custom_network_nodes',
    'tests/test_network.py::test_gene_symbol_conversion_preserves_unknown_identifier',
    'tests/test_network.py::test_sif_import_merges_opposite_signs',
]))
