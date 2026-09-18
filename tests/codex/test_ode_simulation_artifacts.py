from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.codex.ode_simulation_artifacts import validate_simulations


class ODESimulationArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = 'runs/ode-modeler/session/'
        self.run = self.root / self.prefix / 'simulate_fixture'
        self.run.mkdir(parents=True)
        self.revision = 'rev_' + 'a' * 32
        self.report = {'numerical_valid': True, 'conditions': [{'name': 'test'}], 'time_span': [0, 1]}
        self.request = self.run / 'request.json'
        self.request.write_text(json.dumps({'revision': self.revision}))
        self.report_path = self.run / 'simulation.json'
        self.write_report()
        self.csv = 'condition,time,A\ntest,0,1\ntest,1,0.9\n'
        for name in ('species.csv', 'observables.csv'):
            (self.run / name).write_text(self.csv)
        self.files = {path.relative_to(self.root).as_posix(): path for path in self.run.iterdir()}
        self.ode = {'revision': self.revision, 'simulation_paths': [self.report_path.relative_to(self.root).as_posix()]}

    def write_report(self):
        self.report_path.write_text(json.dumps(self.report))

    def validate(self):
        validate_simulations(self.ode, self.root, self.files, self.prefix)

    def test_existing_minimal_fixture_remains_valid(self):
        self.validate()

    def test_backend_condition_records_and_distinct_observables(self):
        self.report['conditions'] = [
            {'name': 'test', 'parameters': {'k': 0.1}, 'initials': {'A': 1.0}},
            {'name': 'treated', 'parameters': {'k': 0.2}, 'initials': {'A': 0.5}},
        ]
        self.write_report()
        (self.run / 'species.csv').write_text(self.csv + 'treated,0,0.5\ntreated,1,0.4\n')
        (self.run / 'observables.csv').write_text(
            'condition,time,activity\ntest,0,2\ntest,1,1.8\ntreated,0,1\ntreated,1,0.8\n')
        self.validate()

    def test_no_simulation_claim_requires_no_files(self):
        validate_simulations({'simulation_paths': []}, self.root, {}, self.prefix)

    def test_simulation_report_and_request_must_be_listed(self):
        for path in (self.report_path, self.request, self.run / 'species.csv', self.run / 'observables.csv'):
            relative = path.relative_to(self.root).as_posix()
            with self.subTest(path=path.name):
                original = self.files.pop(relative)
                with self.assertRaises(ValueError):
                    self.validate()
                self.files[relative] = original

    def test_request_revision_and_report_session_must_match(self):
        self.request.write_text(json.dumps({'revision': 'rev_' + 'b' * 32}))
        with self.assertRaisesRegex(ValueError, 'selected revision'):
            self.validate()
        self.request.write_text(json.dumps({'revision': self.revision}))
        with self.assertRaisesRegex(ValueError, 'listed scenario'):
            validate_simulations(self.ode, self.root, self.files, 'runs/ode-modeler/other/')

    def test_duplicate_or_malformed_simulation_paths_are_rejected(self):
        for paths in ('simulation.json', [None], [self.ode['simulation_paths'][0]] * 2):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                validate_simulations({'simulation_paths': paths}, self.root, self.files, self.prefix)

    def test_report_must_claim_actual_success(self):
        for value in (False, None, 'true', 1):
            with self.subTest(value=value):
                self.report['numerical_valid'] = value
                self.write_report()
                with self.assertRaisesRegex(ValueError, 'successful'):
                    self.validate()

    def test_conditions_require_unique_named_objects(self):
        for conditions in ('invented', {}, [], ['test'], [None], [{}], [{'name': []}],
                           [{'name': ''}], [{'name': ' '}], [{'name': 'test'}] * 2):
            with self.subTest(conditions=conditions):
                self.report['conditions'] = conditions
                self.write_report()
                with self.assertRaises(ValueError):
                    self.validate()

    def test_actual_condition_quantities_must_be_numerical_when_present(self):
        original = copy.deepcopy(self.report)
        for field in ('parameters', 'initials'):
            for values in (None, [], {'k': '0.1'}, {'k': True}, {'k': float('nan')}, {'': 1}):
                with self.subTest(field=field, values=values):
                    self.report = copy.deepcopy(original)
                    self.report['conditions'][0][field] = values
                    self.write_report()
                    with self.assertRaises(ValueError):
                        self.validate()

    def test_time_span_requires_finite_increasing_numeric_bounds(self):
        for span in ('invented', {}, [], [0], [0, 1, 2], ['0', 1], [False, 1],
                     [0, None], [0, float('inf')], [float('nan'), 1], [0, 10 ** 400], [1, 0], [0, 0]):
            with self.subTest(span=span):
                self.report['time_span'] = span
                self.write_report()
                with self.assertRaises(ValueError):
                    self.validate()

    def test_csv_requires_condition_time_and_real_data_columns(self):
        for content in ('', 'time\n999\n', 'condition,time\ntest,0\ntest,1\n',
                        'condition,A\ntest,1\n', 'condition,time,A,A\ntest,0,1,2\n',
                        'condition,time,\ntest,0,1\n'):
            with self.subTest(content=content):
                (self.run / 'species.csv').write_text(content)
                with self.assertRaises(ValueError):
                    self.validate()

    def test_csv_rejects_bad_rows_and_nonfinite_numeric_values(self):
        for value in ('nan', 'inf', '-inf', '', 'not-numeric'):
            with self.subTest(value=value):
                (self.run / 'species.csv').write_text(f'condition,time,A\ntest,0,{value}\ntest,1,1\n')
                with self.assertRaises(ValueError):
                    self.validate()
        for row in ('test,0', 'test,0,1,extra', 'test,nan,1', 'test,0,"unterminated'):
            with self.subTest(row=row):
                (self.run / 'species.csv').write_text(f'condition,time,A\n{row}\ntest,1,1\n')
                with self.assertRaises(ValueError):
                    self.validate()

    def test_csv_conditions_must_match_every_reported_condition(self):
        (self.run / 'species.csv').write_text(self.csv.replace('test,', 'invented,'))
        with self.assertRaisesRegex(ValueError, 'undeclared condition'):
            self.validate()
        (self.run / 'species.csv').write_text(self.csv)
        self.report['conditions'].append({'name': 'missing'})
        self.write_report()
        with self.assertRaisesRegex(ValueError, 'missing a reported condition'):
            self.validate()

    def test_each_trajectory_must_cover_bounds_with_increasing_times(self):
        for times in ((-1, 0, 1), (0, 1, 2), (0.1, 1), (0, 0.9), (0, 1, 0.5), (0, 0, 1)):
            with self.subTest(times=times):
                (self.run / 'species.csv').write_text(
                    'condition,time,A\n' + ''.join(f'test,{time},1\n' for time in times))
                with self.assertRaises(ValueError):
                    self.validate()

    def test_species_and_observable_time_grids_must_match(self):
        (self.run / 'observables.csv').write_text('condition,time,A\ntest,0,1\ntest,0.5,1\ntest,1,1\n')
        with self.assertRaisesRegex(ValueError, 'share condition time grids'):
            self.validate()


if __name__ == '__main__':
    unittest.main()
