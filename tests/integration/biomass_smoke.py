#!/usr/bin/env python3
"""Opt-in software fixture using installed BioMASS; all sessions/artifacts live in /tmp.

Run with the modelling environment's Python -B. No active scientific model, MCP
connection, existing session, environment package, or source checkout is modified.
The enzyme values are the server's shipped software example, not biological claims.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mcp_biomodelling_servers.BioMASS import server
from mcp_biomodelling_servers.BioMASS.contracts import ReactionEdit, SimulationScenario
from mcp_biomodelling_servers.BioMASS.session_manager import BioMASSSessionManager
from scripts.codex.record_ode_artifacts import record
from scripts.codex.ode_artifacts import digest
from scripts.codex.validate_handoff import validate_handoff

ENZYME = '''E + S <--> ES | kf=0.003, kr=0.001 | E=100, S=50, ES=0
ES --> E + P | kf=0.002 | P=0
@obs Free_enzyme: u[E]
@obs Total_enzyme: u[E] + u[ES]
@obs Product: u[P]
@sim tspan: [0, 100]
'''


def main():
    with tempfile.TemporaryDirectory(prefix='biomass-integration-') as tmp:
        temporary = Path(tmp)
        os.environ['NUMBA_CACHE_DIR'] = str(temporary/'numba-cache')
        server_root = temporary/'server'
        # Explicit test double for storage only; authoring and worker code remain real.
        server.session_manager = BioMASSSessionManager(server_root)
        session = server.create_session(label='Software integration fixture only').session_id
        state = server.import_text(ENZYME, biological_context='Synthetic software fixture', session_id=session)
        validation = server.validate_model(check_generation=True, session_id=session)
        assert validation.syntax_valid and validation.generation_valid, validation.model_dump_json()
        generated = server.generate_model(session_id=session)
        simulation = server.run_simulation(SimulationScenario(name='enzyme'), session_id=session)
        assert simulation.details['numerical_valid']
        bundle_result = server.export_model_bundle(session_id=session)
        bundle = Path(next(f.path for f in bundle_result.files if f.name.endswith('.zip')))
        unpacked = temporary/'reproduce'
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(unpacked)
        run_id = Path(next(f.path for f in simulation.files if f.name == 'simulation.json')).parent.name
        reproduction = subprocess.run([sys.executable, '-B', 'run_simulation.py', run_id], cwd=unpacked,
                                      env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                                      capture_output=True, text=True, timeout=60)
        assert reproduction.returncode == 0, reproduction.stderr
        import numpy as np
        import pandas as pd
        for condition in simulation.details['conditions']:
            original = pd.read_csv(next(f.path for f in simulation.files if f.name == 'species.csv'))
            original = original[original['condition'] == condition['name']].drop(columns='condition')
            reproduced = pd.read_csv(unpacked/run_id/f"{condition['name']}_reproduced.csv")
            assert np.allclose(original.values, reproduced.values, rtol=1e-7, atol=1e-8)
        project = temporary/'project'; project.mkdir()
        entries = {}
        for result in (generated, simulation, bundle_result):
            for file in result.files:
                entries[file.path] = {'path': file.path, 'session_id': session, 'sha256': digest(Path(file.path))}
        captured = record(project, server_root, session, 'fixture', list(entries.values()))
        run = project/'runs/ode-modeler'/session
        base = run/'captures/fixture'
        decisions = project/'DECISIONS.md'
        decisions.write_text(f'Decision: software-fixture\nStatus: approved\nSession: {session}\nRevision: {generated.revision}\nAction: export_model_bundle\n')
        approval = run/'export-approval.md'; approval.write_bytes(decisions.read_bytes())
        ode = {'input_kind': 'standalone_text', 'standalone_authorized': True,
               'source_sha256': hashlib.sha256(ENZYME.encode()).hexdigest(),
               'document_version': state.document.version, 'revision': generated.revision,
               'source_identifiers': ['BioMASS shipped enzyme software fixture'], 'evidence_paths': [],
               'revision_path': (base/generated.revision).relative_to(project).as_posix(),
               'simulation_paths': [(base/run_id/'simulation.json').relative_to(project).as_posix()],
               'export_status': 'exported', 'bundle_path': (base/bundle.name).relative_to(project).as_posix(),
               'export_approval': {'decision_id': 'software-fixture', 'sha256': digest(approval),
                                   'path': approval.relative_to(project).as_posix()}}
        h = {'schema_version': 1, 'specialist': 'ode_modeler', 'stage': 'biomass_ode',
             'status': 'completed', 'session_id': session, 'derived_from_session_id': None,
             'actions': ['software fixture'], 'assumptions': [], 'decisions_required': [],
             'validation': {'checks': ['generation', 'simulation', 'bundle reproduction'], 'passed': True},
             'recommended_next_stage': None, 'ode': ode}
        identity = {key: h[key] for key in ('schema_version', 'specialist', 'stage', 'session_id', 'derived_from_session_id', 'ode')}
        (run/'manifest.json').write_text(json.dumps(identity))
        (run/'report.md').write_text('Software integration fixture only; not a scientific model conclusion.\n')
        h['artifacts'] = captured['artifacts'] + [{'path': p.relative_to(project).as_posix(), 'sha256': digest(p)} for p in (run/'manifest.json', run/'report.md', approval)]
        validate_handoff(h, project_root=project)
        # Actual edit preview and optimistic-version rejection in a separate test session.
        editable = server.create_session(label='Preview software fixture').session_id
        edit = ReactionEdit(action='add', reaction_id='conversion', statement='A --> B')
        preview = server.build_reactions(expected_version=0, edits=[edit], session_id=editable)
        assert preview.can_apply and not preview.applied
        assert server.inspect_model(session_id=editable).document.version == 0
        applied = server.build_reactions(expected_version=0, edits=[edit], preview=False, session_id=editable)
        assert applied.applied
        try:
            server.build_reactions(expected_version=0, edits=[edit], preview=False, session_id=editable)
        except ValueError:
            pass
        else:
            raise AssertionError('stale edit unexpectedly succeeded')
        placeholder = server.create_session(label='Placeholder software fixture').session_id
        server.import_text('A --> B\n@obs B: u[B]\n@sim tspan: [0, 10]\n', session_id=placeholder)
        server.generate_model(session_id=placeholder)
        try:
            server.run_simulation(SimulationScenario(name='reject_defaults'), session_id=placeholder)
        except (ValueError, RuntimeError) as error:
            assert 'placeholder' in str(error).lower(), str(error)
        else:
            raise AssertionError('placeholder simulation unexpectedly succeeded')
        print(json.dumps({'passed': True, 'checks': ['syntax and generation', 'enzyme simulation',
            'bundle reproduction within rtol=1e-7 and atol=1e-8', 'verified project artifact capture',
            'typed ODE completion', 'nonmutating edit preview', 'stale version rejection', 'placeholder rejection'],
            'storage': 'temporary software fixtures only'}))


if __name__ == '__main__': main()
