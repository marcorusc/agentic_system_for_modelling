from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from scripts.validate.validate_cycles import first_peak, half_max_time, ordered_peaks, classify_cycles, replicate_seeds
from scripts.validate.boolean_structure import Expression, analyze, LimitExceeded, terminal_scc
from scripts.validate.common import load_series
from scripts.validate.evaluate import evaluate
from scripts.validate.calibrate_cycle import propose


class CycleMetricsTests(unittest.TestCase):
    def test_peak_requires_strict_drop_before_higher_value(self):
        self.assertEqual(first_peak([0,1,2,3,4], [0,.8,.8,.5,.4], .1), 2)
        self.assertIsNone(first_peak([0,1,2,3], [0,.8,.75,.9], .1))
        self.assertIsNone(first_peak([0,1,2], [0,1,1], .1))
        self.assertEqual(half_max_time([0,1,2], [0,.5,1], .5), 1)
        self.assertIsNone(half_max_time([0,1], [0,0], .5))

    def test_order_requires_all_peaks_and_declared_tie_policy(self):
        series = {'A': [0,.8,0], 'B': [0,.7,0]}
        options = {'nodes':['A','B'], 'comparators':['<'], 'metric':'first_peak','drop':.1}
        self.assertFalse(ordered_peaks([0,1,2], series, options)[0])
        options['comparators'] = ['<=']
        self.assertTrue(ordered_peaks([0,1,2], series, options)[0])

    def test_cycle_classification_and_sample_count_boundary(self):
        opts = {'activation_order':['E','C','A'], 'onset_node':'B', 'reset_node':'R', 'threshold':.5, 'sample_count':1, 'minimum_canonical':1,'minimum_fraction':.5}
        series = {'E':[1,1,0,0,0,0], 'C':[0,1,0,0,0,0], 'A':[0,1,0,0,0,0], 'B':[0,1,0,0,1,0], 'R':[0,0,1,0,0,1]}
        ok, metrics = classify_cycles(list(range(6)), series, opts)
        self.assertTrue(ok)
        self.assertEqual(metrics['counts']['canonical'], 1)
        self.assertEqual(metrics['counts']['g1_skip'], 1)
        opts['sample_count'] = 2
        with self.assertRaisesRegex(ValueError, 'single trajectory'):
            classify_cycles(list(range(6)), series, opts)

    def test_spaced_seed_ranges_and_invalid_plans(self):
        self.assertEqual(replicate_seeds(2000,3,0), [0,2000,4000])
        for args in ((0,2,0),(1,0,0),(1,1,-1),(True,2,0),(2000,3,2**31-1)):
            with self.assertRaises(ValueError): replicate_seeds(*args)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def write(self, name, content):
        path = self.root / name; path.write_text(content); return path

    def test_malformed_csv_rejected(self):
        for content in ('', 'Time,A\n', 'Time,A\n0,nan\n', 'Time,A\n0,2\n', 'Time,A\n0,0\n0,1\n', 'Time,A,A\n0,0,0\n', 'Time,A\n0\n', 'Time,A\n0,0,extra\n'):
            with self.subTest(content=content), self.assertRaises((ValueError, TypeError)):
                load_series(self.write('series.csv', content))

    def test_structural_fixed_points_reachable_scc_and_exclusivity(self):
        path = self.write('model.bnet', 'A, !A\nB, A\nC, !A\n')
        passed, result = analyze(path, {'analysis':'reachable_attractors','max_states':8,'expected_count':1,'initial_state':{'A':False,'B':False,'C':False}})
        self.assertTrue(passed)
        self.assertEqual(result['reachable_states'],8)
        self.assertEqual(result['terminal_sccs'][0]['size'],8)
        self.assertTrue(analyze(path, {'analysis':'fixed_points','max_states':8,'expected_count':0})[0])
        self.assertTrue(analyze(path, {'analysis':'readout_exclusivity','max_states':8,'readout_nodes':['B','C']})[0])
        path.write_text('A, A\nB, A\nC, A\n')
        self.assertFalse(analyze(path, {'analysis':'readout_exclusivity','max_states':8,'readout_nodes':['B','C']})[0])

    def test_structural_bound_and_safe_parser(self):
        path = self.write('model.bnet', 'A, !A\nB, A\n')
        for mode in ('fixed_points','reachable_attractors'):
            with self.assertRaises(LimitExceeded):
                analyze(path, {'analysis':mode,'max_states':1,'expected_count':1,'initial_state':{'A':False,'B':False}})
        for expression in ('__import__("os")', 'A.attr', 'A + B', 'A B', 'A &', 'Unknown'):
            with self.subTest(expression=expression), self.assertRaises(ValueError): Expression(expression, ['A','B'])
        self.assertTrue(Expression('!A & (B | 0)', ['A','B'])(2))

    def test_scc_terminal_components_include_isolated_fixed_point(self):
        parts = terminal_scc({0:[1],1:[2],2:[1],3:[]})
        self.assertEqual({frozenset(p) for p in parts}, {frozenset({1,2}),frozenset({3})})

    def test_evaluate_records_hashes_and_incomplete_bound(self):
        self.write('model.bnet','A, !A\nB, A\n')
        config = {'schema_version':1,'criteria':[{'criterion_id':'V1','method':'boolean_structure','inputs':['model.bnet'],'options':{'analysis':'fixed_points','max_states':1,'expected_count':0}}]}
        self.write('criteria.yaml', json.dumps(config))
        result = evaluate(self.root,'criteria.yaml')
        self.assertEqual(result['results'][0]['status'],'incomplete')
        self.assertEqual(result['results'][0]['inputs'][0]['path'],'model.bnet')
        self.assertEqual(len(result['criteria']['sha256']),64)
        config['criteria'][0]['options']['max_states'] = 4
        self.write('criteria.yaml', json.dumps(config))
        self.assertEqual(evaluate(self.root,'criteria.yaml')['results'][0]['status'],'passed')
        config['criteria'][0]['inputs'] = ['/tmp/outside']
        self.write('criteria.yaml', json.dumps(config))
        self.assertEqual(evaluate(self.root,'criteria.yaml')['results'][0]['status'],'incomplete')

    def test_calibration_proposes_explicit_scaling_and_handles_no_cycles(self):
        self.write('single.csv','Time,A\n0,1\n1,0\n2,1\n3,0\n4,1\n5,0\n')
        config = {'schema_version':1,'inputs':['single.csv'],'sample_count':1,'threshold':.5,
                  'target_duration':10,'target_unit':'minutes','source_time_unit':'declared simulation unit',
                  'phases':[{'name':'P0','node':'A','on':True},{'name':'P1','node':'A','on':False}]}
        self.write('calibration.yaml',json.dumps(config))
        result = propose(self.root,'calibration.yaml')
        self.assertEqual(result['status'],'proposed'); self.assertEqual(result['scaling'],5)
        self.assertTrue(result['requires_researcher_approval'])
        self.write('single.csv','Time,A\n0,0\n1,0\n')
        result = propose(self.root,'calibration.yaml')
        self.assertEqual(result['status'],'incomplete'); self.assertIsNone(result['scaling'])
        self.assertIsNone(result['phase_dwell_mean']['P1'])


class ValidationReviewRegressions(unittest.TestCase):
    setUp = ArtifactTests.setUp
    tearDown = ArtifactTests.tearDown
    write = ArtifactTests.write
    def test_rule_exclusivity_does_not_prove_lagged_state_exclusivity(self):
        path = self.write('readouts.bnet', 'A, !A\nB, A\nC, !A\n')
        options = {'analysis': 'readout_exclusivity', 'max_states': 8, 'readout_nodes': ['B', 'C']}
        passed, result = analyze(path, options)
        self.assertTrue(passed)
        self.assertFalse(result['proves_asynchronous_state_exclusivity'])
        options.update(analysis='reachable_readout_exclusivity', initial_state={'A':False, 'B':False, 'C':False})
        passed, result = analyze(path, options)
        self.assertFalse(passed)
        self.assertEqual(result['simultaneously_active_nodes'], ['B','C'])

    def test_reachable_exclusivity_checks_initial_state_and_limits(self):
        path = self.write('readouts.bnet', 'A, A\nB, A\nC, !A\n')
        options = {'analysis': 'reachable_readout_exclusivity', 'max_states': 8, 'readout_nodes': ['B','C'],
                   'initial_state': {'A':False,'B':False,'C':False}}
        passed, result = analyze(path, options)
        self.assertTrue(passed)
        self.assertTrue(result['proves_asynchronous_state_exclusivity'])
        options['initial_state'].update(B=True,C=True)
        self.assertFalse(analyze(path, options)[0])
        options['initial_state'].update(B=False,C=False)
        options['max_states'] = 1
        with self.assertRaises(LimitExceeded): analyze(path, options)

    def test_reachable_analysis_accepts_bounded_22_node_readout_model(self):
        nodes = [f'N{i}' for i in range(22)]
        path = self.write('model.bnet', ''.join(f'{n}, {n}\n' for n in nodes))
        passed, result = analyze(path, {'analysis':'reachable_attractors','max_states':1,'expected_count':1,
                                       'initial_state':{n:False for n in nodes}})
        self.assertTrue(passed)
        self.assertEqual(result['reachable_states'],1)

    def test_empty_criteria_cannot_pass_vacuously(self):
        self.write('criteria.yaml', json.dumps({'schema_version':1,'criteria':[]}))
        with self.assertRaisesRegex(ValueError, 'nonempty'): evaluate(self.root, 'criteria.yaml')

    def test_calibration_requires_cycles_in_every_declared_trajectory(self):
        self.write('complete.csv', 'Time,A\n0,1\n1,0\n2,1\n3,0\n')
        self.write('incomplete.csv', 'Time,A\n0,0\n1,0\n')
        config = {'schema_version':1,'inputs':['complete.csv','incomplete.csv'],'sample_count':1,'threshold':.5,
                  'target_duration':10,'target_unit':'minutes','source_time_unit':'simulation unit',
                  'phases':[{'name':'P0','node':'A','on':True},{'name':'P1','node':'A','on':False}]}
        self.write('calibration.yaml', json.dumps(config))
        result = propose(self.root, 'calibration.yaml')
        self.assertEqual(result['mean_cycle_duration'],2)
        self.assertEqual(result['status'],'incomplete')
        self.assertFalse(result['all_inputs_have_complete_cycles'])
        self.assertIsNone(result['scaling'])
