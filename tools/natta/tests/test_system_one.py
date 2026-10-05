import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import system_one as s1  # noqa: E402

QUESTION = s1.ChoiceQuestion('Which capability?', (
    ('status', 'Inspect status.'), ('build', 'Compile.'), ('no_match', None)))


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def respond(payload):
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return mock.patch.object(s1.urllib.request, 'urlopen', return_value=FakeResponse(raw))


def http_error(code):
    return urllib.error.HTTPError('https://x', code, 'err', {}, io.BytesIO(b'secret detail'))


def jev_answer(choice='build', probs=None, confidence=0.9):
    probs = probs or {'status': 0.05, 'build': 0.9, 'no_match': 0.05}
    return {'model': 'jev-latest', 'usage': {'input_tokens': 1, 'output_tokens': 1},
            'answers': {'capability': {'type': 'choice', 'choice': choice,
                                       'probabilities': probs, 'confidence': confidence}}}


class ConfigTests(unittest.TestCase):
    def load(self, text=None, **env):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'system_one.toml'
            if text is not None:
                path.write_text(text)
            return s1.load_config(path, environ=env)

    def test_defaults_are_jev(self):
        config = self.load()
        self.assertEqual((config.backend, config.model, config.min_confidence), ('jev', 'jev-latest', 0.5))
        self.assertEqual(config.jev.api_key_env, 'TYPESAFE_API_KEY')

    def test_file_selects_ollama(self):
        config = self.load('backend = "ollama"\nmin_confidence = 0.7\n[ollama]\nmodel = "llama3.2:3b"\nhost = "http://gpu-box:11434/"\n')
        self.assertEqual((config.backend, config.model, config.ollama.host), ('ollama', 'llama3.2:3b', 'http://gpu-box:11434'))
        self.assertEqual(config.min_confidence, 0.7)

    def test_env_overrides_file(self):
        config = self.load('backend = "ollama"\n', NATTA_SYSTEM_ONE_BACKEND='jev', NATTA_JEV_MODEL='jev-1.13.0',
                           NATTA_SYSTEM_ONE_MIN_CONFIDENCE='0.8')
        self.assertEqual((config.backend, config.model, config.min_confidence), ('jev', 'jev-1.13.0', 0.8))

    def test_invalid_config_fails_closed(self):
        for text in ('backend = "openai"\n', 'unknown = 1\n', 'schema_version = 2\n', '[jev]\napi_key = "sk"\n',
                     'min_confidence = 2\n', '[ollama]\nhost = "file:///etc"\n', 'not toml ==', '[jev]\nmax_retries = true\n'):
            with self.subTest(text=text), self.assertRaises(s1.ProviderError) as caught:
                self.load(text)
            self.assertEqual(caught.exception.code, 'config_invalid')
        with self.assertRaises(s1.ProviderError):
            self.load(NATTA_SYSTEM_ONE_MIN_CONFIDENCE='high')


class JevTests(unittest.TestCase):
    def backend(self, **env):
        return s1.JevBackend(s1.JevConfig(), environ={'TYPESAFE_API_KEY': 'k-123', **env}, sleep=lambda _: None)

    def test_request_shape_and_answer(self):
        with respond(jev_answer()) as urlopen:
            answers = self.backend().ask({'request': 'build it'}, {'capability': QUESTION})
        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, s1.JEV_ENDPOINT)
        self.assertEqual(request.get_header('Authorization'), 'Bearer k-123')
        self.assertEqual(body, {'state': {'request': 'build it'}, 'model': 'jev-latest', 'questions': {
            'capability': {'type': 'choice', 'instructions': 'Which capability?',
                           'criteria': {'status': 'Inspect status.', 'build': 'Compile.', 'no_match': None}}}})
        answer = answers['capability']
        self.assertEqual((answer.choice, answer.confidence), ('build', 0.9))
        self.assertEqual(list(answer.probabilities), ['status', 'build', 'no_match'])

    def test_missing_key_never_calls_network(self):
        with respond(jev_answer()) as urlopen, self.assertRaises(s1.ProviderError) as caught:
            s1.JevBackend(s1.JevConfig(), environ={}).ask('x', {'capability': QUESTION})
        self.assertEqual(caught.exception.code, 'credentials_missing')
        urlopen.assert_not_called()

    def test_invalid_answers_fail_closed(self):
        bad = [
            jev_answer(choice='deploy'),
            jev_answer(probs={'status': 0.5, 'build': 0.5}),
            jev_answer(probs={'status': 0.5, 'build': 0.9, 'no_match': 0.1}),
            jev_answer(choice='status'),  # not the modal option
            jev_answer(confidence=1.5),
            jev_answer(confidence=True),
            {'answers': {}},
            {'answers': {'capability': {'type': 'noul', 'noul': 0.9}}},
            {'answers': {'capability': None, 'extra': {}}},
            [],
        ]
        for payload in bad:
            with self.subTest(payload=payload), respond(payload), self.assertRaises(s1.ProviderError) as caught:
                self.backend().ask('x', {'capability': QUESTION})
            self.assertEqual(caught.exception.code, 'invalid_response')

    def test_duplicate_keys_and_non_json_fail_closed(self):
        for raw in (b'{"answers": {}, "answers": {}}', b'not json', b'\xff'):
            with self.subTest(raw=raw), respond(raw), self.assertRaises(s1.ProviderError) as caught:
                self.backend().ask('x', {'capability': QUESTION})
            self.assertEqual(caught.exception.code, 'invalid_response')

    def test_http_errors_map_to_bounded_codes(self):
        for status, code in ((401, 'credentials_missing'), (422, 'rejected'), (500, 'rejected')):
            with self.subTest(status=status), mock.patch.object(s1.urllib.request, 'urlopen', side_effect=http_error(status)), \
                    self.assertRaises(s1.ProviderError) as caught:
                self.backend().ask('x', {'capability': QUESTION})
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn('secret', str(caught.exception))

    def test_rate_limit_retries_are_bounded(self):
        with mock.patch.object(s1.urllib.request, 'urlopen', side_effect=[http_error(429), http_error(529), http_error(429)]) as urlopen, \
                self.assertRaises(s1.ProviderError) as caught:
            self.backend().ask('x', {'capability': QUESTION})
        self.assertEqual((caught.exception.code, urlopen.call_count), ('rate_limited', 3))
        with mock.patch.object(s1.urllib.request, 'urlopen', side_effect=[http_error(529), FakeResponse(json.dumps(jev_answer()).encode())]):
            self.assertEqual(self.backend().ask('x', {'capability': QUESTION})['capability'].choice, 'build')

    def test_truncated_response_is_unreachable_not_an_exception(self):
        import http.client
        with mock.patch.object(s1.urllib.request, 'urlopen', side_effect=http.client.IncompleteRead(b'')), \
                self.assertRaises(s1.ProviderError) as caught:
            self.backend().ask('x', {'capability': QUESTION})
        self.assertEqual(caught.exception.code, 'unreachable')

    def test_network_failures(self):
        for error, code in ((urllib.error.URLError('down'), 'unreachable'), (TimeoutError(), 'timeout')):
            with self.subTest(code=code), mock.patch.object(s1.urllib.request, 'urlopen', side_effect=error), \
                    self.assertRaises(s1.ProviderError) as caught:
                self.backend().ask('x', {'capability': QUESTION})
            self.assertEqual(caught.exception.code, code)


def ollama_reply(content, logprobs=None):
    data = {'model': 'qwen3:4b', 'message': {'role': 'assistant', 'content': content}, 'done': True}
    if logprobs is not None:
        data['logprobs'] = logprobs
    return data


class OllamaTests(unittest.TestCase):
    def backend(self):
        return s1.OllamaBackend(s1.OllamaConfig(host='http://ollama.local:11434'))

    def test_request_is_constrained_to_letters(self):
        with respond(ollama_reply('{"choice":"B"}')) as urlopen:
            answer = self.backend().ask({'request': 'build'}, {'q': QUESTION})['q']
        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, 'http://ollama.local:11434/api/chat')
        self.assertEqual(body['format']['properties']['choice']['enum'], ['A', 'B', 'C'])
        self.assertEqual((body['stream'], body['think'], body['logprobs'], body['options']['temperature']), (False, False, True, 0))
        self.assertIn('A. status: Inspect status.', body['messages'][1]['content'])
        self.assertIn('C. no_match', body['messages'][1]['content'])
        self.assertEqual((answer.choice, answer.probabilities, answer.confidence), ('build', None, None))

    def test_probabilities_from_logprobs(self):
        logprobs = [
            {'token': '{"', 'logprob': -0.01, 'top_logprobs': []},
            {'token': 'choice', 'logprob': -0.01, 'top_logprobs': []},
            {'token': '":"', 'logprob': -0.01, 'top_logprobs': []},
            {'token': 'B', 'logprob': math.log(0.8), 'top_logprobs': [
                {'token': 'B', 'logprob': math.log(0.8)}, {'token': 'A', 'logprob': math.log(0.15)},
                {'token': ' C', 'logprob': math.log(0.03)}, {'token': 'Z', 'logprob': math.log(0.02)}]},
            {'token': '"}', 'logprob': -0.01, 'top_logprobs': []},
        ]
        with respond(ollama_reply('{"choice": "B"}', logprobs)):
            answer = self.backend().ask('x', {'q': QUESTION})['q']
        self.assertEqual(answer.choice, 'build')
        self.assertAlmostEqual(sum(answer.probabilities.values()), 1)
        self.assertAlmostEqual(answer.probabilities['build'], 0.8 / 0.98)
        # Same statistic as Jev: (n * p_max - 1) / (n - 1).
        self.assertAlmostEqual(answer.confidence, (3 * 0.8 / 0.98 - 1) / 2)

    def test_bad_outputs_fail_closed(self):
        for content in ('B', '{"choice":"D"}', '{"choice":"B","why":"x"}', '{"choice":"B","choice":"A"}', None, '[]'):
            with self.subTest(content=content), respond(ollama_reply(content)), self.assertRaises(s1.ProviderError) as caught:
                self.backend().ask('x', {'q': QUESTION})
            self.assertEqual(caught.exception.code, 'invalid_response')

    def test_thinking_flag_is_optional(self):
        backend = s1.OllamaBackend(s1.OllamaConfig(disable_thinking=False))
        with respond(ollama_reply('{"choice":"A"}')) as urlopen:
            backend.ask('x', {'q': QUESTION})
        self.assertNotIn('think', json.loads(urlopen.call_args.args[0].data))

    def test_too_many_options(self):
        question = s1.ChoiceQuestion('q', tuple((f'o{i}', None) for i in range(27)))
        with self.assertRaises(s1.ProviderError):
            self.backend().ask('x', {'q': question})


class GateTests(unittest.TestCase):
    def test_threshold(self):
        self.assertTrue(s1.meets_threshold(s1.ChoiceAnswer('a', confidence=0.6), 0.5))
        self.assertFalse(s1.meets_threshold(s1.ChoiceAnswer('a', confidence=0.4), 0.5))
        self.assertTrue(s1.meets_threshold(s1.ChoiceAnswer('a', confidence=0.5), 0.5))
        # Missing confidence (Ollama without logprobs) never passes, even at zero.
        self.assertFalse(s1.meets_threshold(s1.ChoiceAnswer('a'), 0.5))
        self.assertFalse(s1.meets_threshold(s1.ChoiceAnswer('a'), 0))

    def test_choice_confidence_matches_typesafe_formula(self):
        self.assertAlmostEqual(s1.choice_confidence({'a': 1.0, 'b': 0.0}), 1)
        self.assertAlmostEqual(s1.choice_confidence({'a': 0.5, 'b': 0.5}), 0)
        # Documented example: (0.6, 0.3, 0.1) and (0.6, 0.2, 0.2) are both 0.4.
        self.assertAlmostEqual(s1.choice_confidence({'a': 0.6, 'b': 0.3, 'c': 0.1}), 0.4)
        self.assertAlmostEqual(s1.choice_confidence({'a': 0.6, 'b': 0.2, 'c': 0.2}), 0.4)

    def test_question_validation(self):
        for options in ((), (('a', None),), (('a', None), ('a', None)), (('', None), ('b', None))):
            with self.subTest(options=options), self.assertRaises(ValueError):
                s1.ChoiceQuestion('q', options)
        with self.assertRaises(ValueError):
            s1.ChoiceQuestion(' ', (('a', None), ('b', None)))

    def test_backend_selection(self):
        self.assertIsInstance(s1.backend_for(s1.Config()), s1.JevBackend)
        self.assertIsInstance(s1.backend_for(s1.Config(backend='ollama')), s1.OllamaBackend)


class AskTests(unittest.TestCase):
    def test_jev_judgment_records_served_model_and_one_request(self):
        config = s1.Config()
        with respond({**jev_answer(), 'model': 'jev-1.13.0'}):
            judgment = s1.ask(config, 'x', {'capability': QUESTION}, environ={'TYPESAFE_API_KEY': 'k'})
        self.assertEqual((judgment.backend, judgment.model, judgment.requests), ('jev', 'jev-1.13.0', 1))
        self.assertEqual(judgment.answers['capability'].choice, 'build')

    def test_unrecognized_served_model_falls_back_to_configured_name(self):
        with respond({**jev_answer(), 'model': 'bad model\nname'}):
            judgment = s1.ask(s1.Config(), 'x', {'capability': QUESTION}, environ={'TYPESAFE_API_KEY': 'k'})
        self.assertEqual(judgment.model, 'jev-latest')

    def test_ollama_counts_one_request_per_question(self):
        config = s1.Config(backend='ollama')
        with respond(ollama_reply('{"choice":"A"}')) as urlopen:
            # urlopen is a single fake response; reuse is fine for counting calls.
            urlopen.side_effect = lambda *a, **k: FakeResponse(json.dumps(ollama_reply('{"choice":"A"}')).encode())
            judgment = s1.ask(config, 'x', {'a': QUESTION, 'b': QUESTION})
        self.assertEqual((judgment.backend, judgment.requests, urlopen.call_count), ('ollama', 2, 2))

    def test_backend_answers_are_revalidated(self):
        class Rogue:
            requests, served_model = 1, None
            def __init__(self, answers): self.answers = answers
            def ask(self, state, questions): return self.answers
        for answers in ({}, {'capability': s1.ChoiceAnswer('rm -rf /')}, {'capability': 'build'},
                        {'capability': s1.ChoiceAnswer('build'), 'extra': s1.ChoiceAnswer('build')}):
            with self.subTest(answers=answers), mock.patch.object(s1, 'backend_for', return_value=Rogue(answers)), \
                    self.assertRaises(s1.ProviderError) as caught:
                s1.ask(s1.Config(), 'x', {'capability': QUESTION})
            self.assertEqual(caught.exception.code, 'invalid_response')

    def test_questions_must_be_typed(self):
        for questions in ({}, {'q': {'type': 'choice'}}, [QUESTION]):
            with self.subTest(questions=questions), self.assertRaises(s1.ProviderError):
                s1.ask(s1.Config(), 'x', questions)


class DoctorTests(unittest.TestCase):
    def rows(self, environ, get_json=None):
        environ = {'NATTA_SYSTEM_ONE_CONFIG': '/nonexistent/system_one.toml', **environ}
        fail = lambda *a: (_ for _ in ()).throw(AssertionError('network'))
        return s1.doctor_checks(environ, get_json or fail)

    def test_jev_reports_key_presence_never_value_and_no_network(self):
        rows = self.rows({'TYPESAFE_API_KEY': 'sk-secret-value'})
        self.assertTrue(all(ok for ok, _ in rows))
        self.assertNotIn('sk-secret-value', json.dumps(rows))
        self.assertIn('backend=jev model=jev-latest min_confidence=0.50', rows[0][1])
        self.assertEqual(self.rows({})[1], (False, 'TypeSafe API key missing in TYPESAFE_API_KEY; service/auth not probed'))

    def test_ollama_reachability_and_model_presence_without_inference(self):
        calls = []
        def get_json(url, timeout):
            calls.append(url)
            return {'version': '0.12.11'} if url.endswith('/api/version') else {'models': [{'name': 'qwen3:4b'}]}
        rows = self.rows({'NATTA_SYSTEM_ONE_BACKEND': 'ollama'}, get_json)
        self.assertEqual(calls, ['http://127.0.0.1:11434/api/version', 'http://127.0.0.1:11434/api/tags'])
        self.assertTrue(all(ok for ok, _ in rows))
        missing = self.rows({'NATTA_SYSTEM_ONE_BACKEND': 'ollama', 'NATTA_OLLAMA_MODEL': 'other'}, get_json)
        self.assertEqual(missing[-1], (False, 'Ollama model other not installed'))
        def down(url, timeout): raise urllib.error.URLError('refused')
        self.assertFalse(self.rows({'NATTA_SYSTEM_ONE_BACKEND': 'ollama'}, down)[-1][0])

    def test_invalid_configuration_is_one_unavailable_row(self):
        rows = self.rows({'NATTA_SYSTEM_ONE_BACKEND': 'codex'})
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0][0])


if __name__ == '__main__':
    unittest.main()
