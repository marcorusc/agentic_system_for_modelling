from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from scripts.validate.scenario_contrast import contrast
from scripts.validate.evaluate import evaluate

ROLES = ('test_control', 'test_perturbed', 'reference_control', 'reference_perturbed')


def series(*finals, nodes=('Proliferation', 'Survival')):
    """One trajectory whose node values ramp from 0 to the given final values."""
    return {n: [0.0, v / 2, v] for n, v in zip(nodes, finals)}


class ContrastTests(unittest.TestCase):
    options = {'readouts': ['Proliferation'], 'margin': 0.1, 'combine': 'all', 'statistic': 'final'}

    def test_drop_must_exceed_reference_by_margin(self):
        ok, metrics = contrast([series(.9, .9), series(.2, .2), series(.9, .9), series(.7, .7)], self.options)
        self.assertTrue(ok)
        row = metrics['readouts']['Proliferation']
        self.assertAlmostEqual(row['test_drop'], .7)
        self.assertAlmostEqual(row['reference_drop'], .2)
        self.assertTrue(row['passed'])
        self.assertEqual(metrics['input_roles'], list(ROLES))

    def test_difference_equal_to_margin_fails(self):
        ok, metrics = contrast([series(.5, .5), series(.25, .25), series(.5, .5), series(.375, .375)],
                               dict(self.options, margin=0.125))
        self.assertAlmostEqual(metrics['readouts']['Proliferation']['difference'], .125)
        self.assertFalse(ok)

    def test_combine_all_and_any(self):
        inputs = [series(.9, .9), series(.2, .85), series(.9, .9), series(.7, .7)]
        both = dict(self.options, readouts=['Proliferation', 'Survival'])
        self.assertFalse(contrast(inputs, both)[0])
        self.assertTrue(contrast(inputs, dict(both, combine='any'))[0])

    def test_tail_mean_uses_last_points(self):
        test_control = {'Proliferation': [0, .8, 1.0]}
        ok, metrics = contrast([test_control, {'Proliferation': [0, 0, 0]}, {'Proliferation': [0, 1, 1]},
                                {'Proliferation': [0, 1, 1]}],
                               dict(self.options, statistic='tail_mean', tail_points=2))
        self.assertAlmostEqual(metrics['readouts']['Proliferation']['test_control'], .9)
        self.assertTrue(ok)

    def test_invalid_options_rejected(self):
        inputs = [series(.9, .9)] * 4
        for bad in ({k: v for k, v in self.options.items() if k != 'margin'},
                    dict(self.options, margin=-0.1), dict(self.options, margin=True),
                    dict(self.options, readouts=[]), dict(self.options, readouts=['P', 'P']),
                    dict(self.options, readouts=['Missing']), dict(self.options, combine='mean'),
                    dict(self.options, statistic='tail_mean'), dict(self.options, statistic='tail_mean', tail_points=9),
                    dict(self.options, tail_points=2), dict(self.options, extra=1)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                contrast(inputs, bad)
        with self.assertRaises(ValueError):
            contrast(inputs[:3], self.options)


class EvaluateIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        for name, value in zip(ROLES, (.9, .2, .9, .7)):
            (self.root / f'{name}.csv').write_text(f'Time,Proliferation\n0,0\n1,{value}\n')
    def tearDown(self): self.temp.cleanup()

    def run_with(self, inputs, options):
        config = {'schema_version': 1, 'criteria': [{'criterion_id': 'V-LUAD-1', 'method': 'scenario_contrast',
                                                    'inputs': inputs, 'options': options}]}
        (self.root / 'criteria.yaml').write_text(json.dumps(config))
        return evaluate(self.root, 'criteria.yaml')['results'][0]

    def test_joint_inputs_recorded_with_hashes(self):
        inputs = [f'{r}.csv' for r in ROLES]
        result = self.run_with(inputs, ContrastTests.options)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual([i['path'] for i in result['inputs']], inputs)
        self.assertTrue(all(len(i['sha256']) == 64 for i in result['inputs']))
        self.assertIn('readouts', result['metrics'])

    def test_failures_and_incomplete(self):
        inputs = [f'{r}.csv' for r in ROLES]
        self.assertEqual(self.run_with(inputs, dict(ContrastTests.options, margin=.6))['status'], 'failed')
        self.assertEqual(self.run_with(inputs[:3], ContrastTests.options)['status'], 'incomplete')
        self.assertEqual(self.run_with(inputs, dict(ContrastTests.options, readouts=['Survival']))['status'], 'incomplete')
        self.assertEqual(self.run_with(inputs[:3] + ['missing.csv'], ContrastTests.options)['status'], 'incomplete')


if __name__ == '__main__':
    unittest.main()
