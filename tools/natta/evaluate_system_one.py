"""Explicit counted System One evaluation over the public corpora. Never executes.

Runs the configured backend (Jev or Ollama) with the gate disabled
(min_confidence=0), records each answer's confidence, and derives the outcome at
every threshold offline, so a confidence threshold can come from measurement.
Real Jev calls are billed: the exact request count must be declared up front.
"""
import argparse
from dataclasses import replace
from functools import partial
import json
import os
from pathlib import Path
import sys
import tempfile
import time

import natta
import planning
import routing
import system_one

ROOT = Path(__file__).resolve().parent
CORPORA = {
    'routing': ('commit-routing-v2', 'commit-routing-holdout-r1', 'commit-routing-holdout-r2', 'testflight-routing-v1'),
    'planner': ('planner', 'commit-planner-v2', 'testflight-planner-v1'),
}
FILES = {'planner': 'planner-corpus-v1.json'}
THRESHOLDS = tuple(round(i * 0.05, 2) for i in range(20))
NO_ROUTE = {'capability': 'no_match', 'project': None, 'arguments': {}, 'arguments_resolved': False}
NO_PLAN = {'status': 'no_match', 'steps': []}
REGISTRY = '''schema_version = 1
[[projects]]
alias = "example"
aliases = ["example-app"]
name = "Example App"
path = "example"
type = "generic-git"
[[projects]]
alias = "sample"
aliases = ["sampleapp", "sample-app"]
name = "Sample App"
path = "sample"
type = "generic-git"
'''


def load_cases(mode, name):
    if name not in CORPORA[mode]:
        raise ValueError(f'Unknown {mode} corpus: {name}')
    path = ROOT / 'evaluation' / FILES.get(name, f'{name}-corpus.json')
    cases = json.loads(path.read_text())['cases']
    if not cases or any(set(c) != {'id', 'category', 'request', 'expected'} for c in cases):
        raise ValueError('Unexpected corpus shape')
    return cases


def required_requests(mode, backend, cases):
    questions = 1 if mode == 'routing' else 1 + 2 * planning.MAX_STEPS
    return len(cases) * (1 if backend == 'jev' else questions)


def compact_route(result):
    if result.status not in ('matched', 'no_match'):
        return {'status': result.status, 'error': result.error}
    return {'capability': result.capability, 'project': result.project,
            'arguments': dict(result.arguments), 'arguments_resolved': result.arguments_resolved}


def compact_plan(result):
    if result.status != 'planned':
        return {'status': result.status, **({'error': result.error} if result.error else {})}
    return {'status': 'planned', 'steps': [{'capability': s.capability, 'project': s.project,
                                            'arguments': dict(s.arguments)} for s in result.steps]}


def plan_confidence(result):
    """Lowest confidence among deciding answers; None if any is missing."""
    if result.answers is None:
        return None
    try:
        values = [result.answers[q].confidence for q in planning.deciding_questions(result.answers)]
    except planning.InvalidPlan:
        return None
    return None if any(v is None for v in values) else min(values)


def at_threshold(record, threshold, mode):
    """The outcome the production gate would give at this threshold."""
    gated = NO_ROUTE if mode == 'routing' else NO_PLAN
    confidence, predicted = record['confidence'], record['predicted']
    if record['provider_error']:
        return predicted
    if mode == 'planner' and predicted.get('status') not in ('planned', 'no_match'):
        return predicted  # structural rejection happens before the gate
    if confidence is None or confidence < threshold:
        return gated
    return predicted


def metrics(records, mode):
    rows = []
    for threshold in THRESHOLDS:
        outcomes = [(r, at_threshold(r, threshold, mode)) for r in records]
        if mode == 'routing':
            negative = lambda r: r['expected']['capability'] == 'no_match'
            accepted = lambda o: o.get('capability') not in (None, 'no_match')
            # Unsafe: a resolved route for anything other than the gold route.
            unsafe = sum(1 for r, o in outcomes if accepted(o) and o.get('arguments_resolved') and o != r['expected'])
        else:
            negative = lambda r: r['expected']['status'] == 'no_match'
            accepted = lambda o: o.get('status') == 'planned'
            unsafe = sum(1 for r, o in outcomes if accepted(o) and o != r['expected'])
        exact = sum(1 for r, o in outcomes if o == r['expected'])
        negatives = [(r, o) for r, o in outcomes if negative(r)]
        positives = [(r, o) for r, o in outcomes if not negative(r)]
        rows.append({'threshold': threshold, 'exact': exact, 'total': len(records),
                     'exact_accuracy': exact / len(records),
                     'coverage': sum(1 for _, o in positives if accepted(o)) / len(positives) if positives else None,
                     'rejection': sum(1 for _, o in negatives if not accepted(o)) / len(negatives) if negatives else None,
                     'unsafe_accepts': unsafe})
    return rows


def run(mode, corpus, allowed, output, *, limit=None, environ=None):
    environ = os.environ if environ is None else environ
    cases = load_cases(mode, corpus)[:limit] if limit else load_cases(mode, corpus)
    config = system_one.load_config(environ=environ)
    needed = required_requests(mode, config.backend, cases)
    if type(allowed) is not int or allowed != needed:
        raise ValueError(f'This run needs exactly {needed} external requests; pass --allow-external-requests {needed}')
    output = Path(output)
    with open(output, 'x'):  # refuse to overwrite before any request
        pass
    os.chmod(output, 0o600)
    ungated = replace(config, min_confidence=0.0)
    parser = natta.make_parser()
    records, started, complete, requests = [], time.time(), False, 0
    with tempfile.TemporaryDirectory() as tmp:
        registry = Path(tmp) / 'projects.toml'
        registry.write_text(REGISTRY)
        projects = natta.load_registry(registry)
        bindings = natta.handler_bindings()
        try:
            for case in cases:
                if mode == 'routing':
                    result = natta.prepare_route(case['request'], parser, registry,
                                                 selector=partial(routing.select, config=ungated, environ=environ))
                    predicted, confidence = compact_route(result), result.confidence
                    error, model, used = result.status == 'provider_error', result.model, 1
                    detail = {'probabilities': result.as_dict()['probabilities']}
                else:
                    result = planning.propose(case['request'], parser, projects, bindings, config=ungated, environ=environ)
                    predicted, confidence = compact_plan(result), plan_confidence(result)
                    error, model, used = result.status == 'provider_error', result.model, result.external_requests
                    detail = {'answers': result.as_dict()['answers'], 'reason': result.reason}
                requests += used
                records.append({'id': case['id'], 'category': case['category'], 'expected': case['expected'],
                                'predicted': predicted, 'confidence': confidence, 'provider_error': error,
                                'model': model, 'correct_ungated': predicted == case['expected'], **detail})
            complete = True
        finally:
            artifact = {'schema_version': 1, 'evaluation_only': True, 'executed': False,
                        'mode': mode, 'corpus': corpus, 'complete': complete,
                        'backend': config.backend, 'configured_model': config.model,
                        'configured_min_confidence': config.min_confidence,
                        'served_models': sorted({r['model'] for r in records if r['model']}),
                        'declared_external_requests': allowed, 'actual_external_requests': requests,
                        'cases': len(cases), 'provider_failures': sum(r['provider_error'] for r in records),
                        'seconds': time.time() - started,
                        'thresholds': metrics(records, mode) if records else [], 'records': records}
            output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + '\n')
    return artifact


def render(artifact):
    lines = [f"{artifact['mode']} / {artifact['corpus']} on {artifact['backend']} "
             f"({', '.join(artifact['served_models']) or artifact['configured_model']}): "
             f"{artifact['cases']} cases, {artifact['provider_failures']} provider failures, "
             f"{artifact['actual_external_requests']} requests, complete={artifact['complete']}",
             'threshold  exact     coverage  rejection  unsafe']
    fmt = lambda v: '   -  ' if v is None else f'{v:6.2f}'
    for row in artifact['thresholds']:
        lines.append(f"  {row['threshold']:.2f}     {row['exact']:>2}/{row['total']:<3}  {fmt(row['coverage'])}    "
                     f"{fmt(row['rejection'])}     {row['unsafe_accepts']}")
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=sorted(CORPORA))
    parser.add_argument('--corpus', required=True)
    parser.add_argument('--allow-external-requests', type=int, required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--limit', type=int, help='Evaluate only the first N cases (smoke)')
    args = parser.parse_args(argv)
    try:
        artifact = run(args.mode, args.corpus, args.allow_external_requests, args.output, limit=args.limit)
    except (ValueError, FileExistsError, system_one.ProviderError) as exc:
        print(f'evaluate_system_one: {exc}', file=sys.stderr)
        return 2
    print(render(artifact))
    return 0 if artifact['complete'] else 1


if __name__ == '__main__':
    sys.exit(main())
