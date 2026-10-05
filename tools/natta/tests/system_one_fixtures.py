"""Mocked System One judgments for tests. Never makes a network request.

Importing this module isolates the test process from the user's System One
configuration and credentials, so ordinary tests are hermetic.
"""
import os
from pathlib import Path
import sys
from types import MappingProxyType
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import system_one  # noqa: E402

for _name in [k for k in os.environ if k.startswith('NATTA_SYSTEM_ONE_') or k.startswith('NATTA_JEV_')
              or k.startswith('NATTA_OLLAMA_') or k == 'TYPESAFE_API_KEY']:
    del os.environ[_name]
os.environ['NATTA_SYSTEM_ONE_CONFIG'] = str(Path(__file__).resolve().parent / 'fixtures-no-system-one.toml')

DEFAULTS = {'capability': 'no_match', 'scope': 'supported'}


def answer(question, choice, confidence=0.95):
    """A Jev-shaped answer: mass on choice, remainder spread over the other options."""
    ids = question.ids
    if choice not in ids:
        return system_one.ChoiceAnswer(choice)  # deliberately invalid; ask() must reject it
    if confidence is None:
        return system_one.ChoiceAnswer(choice)
    n = len(ids)
    top = confidence * (1 - 1 / n) + 1 / n
    rest = (1 - top) / (n - 1)
    probabilities = {name: (top if name == choice else rest) for name in ids}
    return system_one.ChoiceAnswer(choice, MappingProxyType(probabilities), confidence)


def default_choice(qid):
    return DEFAULTS.get(qid, 'no_match')


class Fake:
    """Callable stand-in for system_one.ask; records calls like a mock."""

    def __init__(self, choices, confidence=0.95, error=None, model=None):
        self.choices, self.confidence, self.error, self.model = dict(choices), confidence, error, model
        self.calls = []

    @property
    def call_count(self):
        return len(self.calls)

    def __call__(self, config, state, questions, environ=None):
        self.calls.append((config, state, dict(questions)))
        if self.error is not None:
            raise self.error
        def confidence(qid):
            if isinstance(self.confidence, dict):
                return self.confidence.get(qid, 0.95)
            return self.confidence
        answers = {qid: answer(q, self.choices.get(qid, default_choice(qid)), confidence(qid))
                   for qid, q in questions.items()}
        for qid, a in answers.items():
            if a.choice not in questions[qid].ids:
                raise system_one.ProviderError('invalid_response')
        requests = 1 if config.backend == 'jev' else len(questions)
        return system_one.Judgment(MappingProxyType(answers), config.backend,
                                   self.model or config.model, requests, 0.01)


def route(choice, confidence=0.95, **kwargs):
    return Fake({'capability': choice}, confidence, **kwargs)


def plan(steps, projects=None, *, scope='supported', confidence=0.95, **kwargs):
    """steps: the capability answered for each goal part, in order.

    projects is accepted for readability at call sites only: planning resolves
    projects deterministically from the goal text, never from System One.
    """
    choices = {'scope': scope}
    for index, cap in enumerate(steps, 1):
        choices[f'step_{index}'] = cap
    return Fake(choices, confidence, **kwargs)


def failing(code='rejected'):
    return Fake({}, error=system_one.ProviderError(code))


def ask(fake):
    """Patch the single System One entry point used by routing and planning."""
    return patch.object(system_one, 'ask', side_effect=fake)


def forbidden(label='provider'):
    return patch.object(system_one, 'ask', side_effect=AssertionError(label))
