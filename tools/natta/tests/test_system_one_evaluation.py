"""Counted System One evaluation; mocked answers, no network, no execution."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import natta
import evaluate_system_one as e
import system_one_fixtures as s1fx


class Corpus:
    """Answer each routing case with its gold capability, at a chosen confidence."""

    def __init__(self, cases, confidence=0.9):
        self.gold = {c['request']: c['expected'] for c in cases}
        self.confidence = confidence

    def __call__(self, config, state, questions, environ=None):
        expected = self.gold[state['request']]
        return s1fx.route(expected['capability'], self.confidence)(config, state, questions, environ)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        patcher = patch.object(natta.semantic_execution, 'dispatch', side_effect=AssertionError('dispatch'))
        patcher.start(); self.addCleanup(patcher.stop)

    def test_budget_must_be_exact_and_declared_before_any_request(self):
        cases = e.load_cases('routing', 'testflight-routing-v1')
        with tempfile.TemporaryDirectory() as tmp:
            _, projects = e.evaluation_projects(tmp)
            self.assertEqual(e.required_requests('routing', 'jev', cases, projects), 12)
            planner = e.load_cases('planner', 'planner')
            jev = e.required_requests('planner', 'jev', planner, projects)
            # Structural rejections (no project, too many parts) make no request.
            self.assertLess(jev, 36)
            self.assertGreater(e.required_requests('planner', 'ollama', planner, projects), 2 * jev)
        with s1fx.forbidden():
            for allowed in (11, 13, 0, True):
                with self.assertRaises(ValueError):
                    e.run('routing', 'testflight-routing-v1', allowed, self.root / 'refused.json', environ={})
        self.assertFalse((self.root / 'refused.json').exists())
        with self.assertRaises(ValueError): e.load_cases('routing', 'planner')

    def test_routing_gold_answers_pass_and_existing_output_is_refused(self):
        cases = e.load_cases('routing', 'commit-routing-v2')
        out = self.root / 'routing.json'
        with s1fx.ask(Corpus(cases)) as ask:
            artifact = e.run('routing', 'commit-routing-v2', 16, out, environ={})
        self.assertEqual((ask.call_count, artifact['actual_external_requests'], artifact['complete']), (16, 16, True))
        self.assertFalse(artifact['executed'])
        row = next(r for r in artifact['thresholds'] if r['threshold'] == 0.5)
        self.assertEqual((row['exact'], row['unsafe_accepts'], row['rejection']), (16, 0, 1.0))
        self.assertEqual(json.loads(out.read_text())['corpus'], 'commit-routing-v2')
        self.assertEqual(out.stat().st_mode & 0o777, 0o600)
        with s1fx.forbidden(), self.assertRaises(FileExistsError):
            e.run('routing', 'commit-routing-v2', 16, out, environ={})

    def test_thresholds_are_derived_offline_from_ungated_answers(self):
        cases = e.load_cases('routing', 'testflight-routing-v1')
        with s1fx.ask(Corpus(cases, confidence=0.6)):
            artifact = e.run('routing', 'testflight-routing-v1', 12, self.root / 'sweep.json', environ={})
        rows = {r['threshold']: r for r in artifact['thresholds']}
        self.assertEqual(rows[0.6]['exact'], 12)
        # Above the answers' confidence, every positive becomes no_match: nothing unsafe, no coverage.
        self.assertEqual((rows[0.65]['coverage'], rows[0.65]['unsafe_accepts'], rows[0.65]['rejection']), (0.0, 0, 1.0))
        self.assertTrue(all(r['confidence'] == 0.6 for r in artifact['records']))

    def test_wrong_confident_routes_are_counted_unsafe(self):
        with s1fx.ask(s1fx.route('build', 0.99)):
            artifact = e.run('routing', 'commit-routing-v2', 16, self.root / 'wrong.json', environ={})
        row = next(r for r in artifact['thresholds'] if r['threshold'] == 0.5)
        self.assertGreater(row['unsafe_accepts'], 0)
        self.assertEqual(row['rejection'], 0.0)

    def test_planner_records_answers_and_minimum_deciding_confidence(self):
        out = self.root / 'plan.json'
        fake = s1fx.plan(['commit'], confidence={'step_1': 0.4})
        with tempfile.TemporaryDirectory() as tmp:
            needed = e.required_requests('planner', 'jev', e.load_cases('planner', 'commit-planner-v2'), e.evaluation_projects(tmp)[1])
        with s1fx.ask(fake) as ask:
            artifact = e.run('planner', 'commit-planner-v2', needed, out, limit=None, environ={})
        self.assertEqual((ask.call_count, artifact['actual_external_requests']), (needed, needed))
        record = next(r for r in artifact['records'] if r['id'] == 'commit-planner-v2-01')
        self.assertEqual(record['confidence'], 0.4)
        self.assertEqual(record['predicted'], record['expected'])
        # The gold plan survives a 0.4 threshold and becomes no_match above it.
        self.assertEqual(e.at_threshold(record, 0.4, 'planner'), record['expected'])
        self.assertEqual(e.at_threshold(record, 0.45, 'planner'), e.NO_PLAN)
        self.assertIn('scope', record['answers'])

    def test_provider_failure_is_recorded_not_fabricated_as_no_match(self):
        with s1fx.ask(s1fx.failing('rate_limited')):
            artifact = e.run('routing', 'testflight-routing-v1', 2, self.root / 'fail.json', limit=2, environ={})
        self.assertEqual(artifact['provider_failures'], 2)
        self.assertEqual(artifact['records'][0]['predicted'], {'status': 'provider_error', 'error': 'rate_limited'})
        self.assertTrue(all(r['exact'] == 0 for r in artifact['thresholds']))

    def test_cli_reports_and_never_executes(self):
        cases = e.load_cases('routing', 'testflight-routing-v1')
        with s1fx.ask(Corpus(cases)), contextlib.redirect_stdout(io.StringIO()) as out:
            code = e.main(['routing', '--corpus', 'testflight-routing-v1', '--allow-external-requests', '12',
                           '--output', str(self.root / 'cli.json')])
        self.assertEqual(code, 0)
        self.assertIn('threshold  exact', out.getvalue())
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(e.main(['routing', '--corpus', 'testflight-routing-v1', '--allow-external-requests', '1',
                                     '--output', str(self.root / 'cli2.json')]), 2)
        self.assertIn('needs exactly 12', err.getvalue())


if __name__ == '__main__': unittest.main()
