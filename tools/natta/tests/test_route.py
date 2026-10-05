"""Production selection boundaries; every System One call is mocked."""
import ast
import contextlib
from dataclasses import FrozenInstanceError
import io
import json
import os
from pathlib import Path
from types import MappingProxyType
import unittest
from unittest.mock import patch
import urllib.error

import natta
import routing
import semantic_catalog as catalog
import system_one
import system_one_fixtures as s1fx


class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *exc): return False


def jev_reply(choice='build', confidence=0.9):
    ids = catalog.TOOLKIT_IDS
    rest = (1 - 0.92) / (len(ids) - 1)
    probabilities = {name: 0.92 if name == choice else rest for name in ids}
    return {'model': 'jev-1.13.0', 'usage': {'input_tokens': 1, 'output_tokens': 1},
            'answers': {'capability': {'type': 'choice', 'choice': choice,
                                       'probabilities': probabilities, 'confidence': confidence}}}


class RouteTests(unittest.TestCase):
    def invoke(self,*args):
        out,err = io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err): code = natta.main(list(args))
        return code,out.getvalue(),err.getvalue()

    def test_parser_json_and_no_execution_options(self):
        for args in (['route','--json','Build Example'],['route','Build Example','--json']):
            parsed=natta.make_parser().parse_args(args)
            self.assertEqual((parsed.command,parsed.request,parsed.json),('route','Build Example',True))
            self.assertFalse(hasattr(parsed,'project'))
        for flag in ('--model','--level','--log','--verbose','--execute','--backend'):
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                natta.make_parser().parse_args(['route','request',flag,'x'])

    def test_build_route_never_calls_build_or_project_inspection(self):
        fake=s1fx.route('build')
        with s1fx.ask(fake), \
             patch.object(natta,'load_registry',return_value=[natta.Project('example', ('example-app',), 'Example App', Path('/uninspected/example'), 'generic-git', {})]), \
             patch.object(natta,'lookup',side_effect=AssertionError('lookup')), \
             patch.object(natta,'git_state',side_effect=AssertionError('app inspection')), \
             patch.object(natta,'orientation',side_effect=AssertionError('app contents')), \
             patch.object(natta.adapters,'resolve',side_effect=AssertionError('build handler')), \
             patch.object(natta,'execute',side_effect=AssertionError('execution')), \
             patch.object(natta,'launch_codex',side_effect=AssertionError('handoff')), \
             patch.object(natta,'ExecutionDirectory',side_effect=AssertionError('workflow')), \
             patch.object(natta.local_model,'doctor_checks',side_effect=AssertionError('Qwen')):
            code,out,err=self.invoke('--registry','/missing','route','--json','Build Example for the simulator')
        self.assertEqual((code,err),(0,''))
        result = json.loads(out)
        decision = result.pop('execution_policy')
        self.assertTrue(decision['eligible'])
        self.assertEqual(decision['authorization'], 'explicit')
        probabilities = result.pop('probabilities')
        self.assertEqual(set(probabilities), set(catalog.TOOLKIT_IDS))
        self.assertAlmostEqual(sum(probabilities.values()), 1)
        self.assertEqual(max(probabilities, key=probabilities.get), 'build')
        self.assertEqual(result,{'status':'matched','capability':'build','provider':'system-one',
            'backend':'jev','model':'jev-latest','min_confidence':0.5,'confidence':0.95,'reason':None,
            'executed':False,'arguments_resolved':True,'error':None,'project':'example',
            'arguments':{},'missing_arguments':[],'resolution_error':None})
        self.assertEqual(fake.call_count,1)

    def test_all_known_choices_and_no_match(self):
        for choice in catalog.TOOLKIT_IDS:
            with s1fx.ask(s1fx.route(choice)): result=routing.select('request')
            self.assertEqual(result.capability,choice)
            self.assertEqual(result.status,'no_match' if choice=='no_match' else 'matched')
            self.assertIs(result.executed,False); self.assertIs(result.arguments_resolved,False)
            self.assertIsNone(result.reason)

    def test_human_no_match_output_exit_zero(self):
        with s1fx.ask(s1fx.route('no_match')):
            code,out,err=self.invoke('route','Commit and push Example')
        self.assertEqual((code,err),(0,''))
        self.assertEqual(out,'Route\n  status: no_match\n  capability: no_match\n  project: none\n'
            '  provider: system-one (jev jev-latest)\n  confidence: 0.95 (minimum 0.50)\n'
            '  resolved: no\n  executed: no\n  authorization: forbidden\n  policy eligible: no\n  policy reason: no_match\n')

    def test_low_or_missing_confidence_is_non_executing_no_match(self):
        for confidence in (0.49, 0.0, None):
            with self.subTest(confidence=confidence), s1fx.ask(s1fx.route('build', confidence)):
                code,out,err=self.invoke('route','--json','Build Example')
            result=json.loads(out)
            self.assertEqual((code,result['status'],result['capability'],result['reason']),(0,'no_match','no_match','low_confidence'))
            self.assertEqual(result['confidence'],confidence)
            self.assertEqual(result['execution_policy']['reason'],'no_match')
            self.assertFalse(result['execution_policy']['eligible'])
            self.assertIsNone(result['project'])
            if confidence is None: self.assertIsNone(result['probabilities'])
            else: self.assertEqual(max(result['probabilities'],key=result['probabilities'].get),'build')
        with s1fx.ask(s1fx.route('build', 0.49)):
            code,out,_=self.invoke('route','Build Example')
        self.assertIn('  confidence: 0.49 (minimum 0.50)\n  reason: low_confidence\n',out)

    def test_threshold_is_configurable_and_never_admits_missing_confidence(self):
        with patch.dict(os.environ,{'NATTA_SYSTEM_ONE_MIN_CONFIDENCE':'0.8'}):
            with s1fx.ask(s1fx.route('build',0.79)): self.assertEqual(routing.select('r').reason,'low_confidence')
            with s1fx.ask(s1fx.route('build',0.8)): self.assertEqual(routing.select('r').status,'matched')
        with patch.dict(os.environ,{'NATTA_SYSTEM_ONE_MIN_CONFIDENCE':'0'}), s1fx.ask(s1fx.route('build',None)):
            self.assertEqual(routing.select('r').reason,'low_confidence')

    def test_unknown_choices_fail_closed_at_routing_boundary(self):
        # Even if a backend (or mock) bypasses ask()'s validation, routing revalidates.
        for choice in ('delete_everything','codex','route'):
            judgment=system_one.Judgment(MappingProxyType({'capability':system_one.ChoiceAnswer(choice,None,1.0)}),'jev','m',1,0.0)
            with patch.object(system_one,'ask',return_value=judgment): result=routing.select('request')
            self.assertEqual((result.status,result.error,result.capability),('provider_error','unknown_choice',None))
        with s1fx.ask(s1fx.route('delete_everything')): result=routing.select('request')
        self.assertEqual((result.status,result.error),('provider_error','malformed_output'))
        self.assertEqual(set(result.as_dict()),{'status','capability','provider','executed','arguments_resolved','error','project',
            'arguments','missing_arguments','resolution_error','execution_policy','backend','model','min_confidence',
            'confidence','probabilities','reason'})

    def test_failures_nonzero_bounded_codes_no_fallback_or_fabricated_no_match(self):
        for code_name, expected in system_one.RESULT_ERRORS.items():
            fake=s1fx.failing(code_name)
            with s1fx.ask(fake):
                code,out,err=self.invoke('route','--json','request')
            result=json.loads(out)
            self.assertEqual(fake.call_count,1)
            self.assertEqual((code,err,result['status'],result['error']),(1,'','provider_error',expected))
            self.assertIsNone(result['capability']); self.assertIs(result['executed'],False)

    def test_jev_http_request_carries_only_request_and_definitions(self):
        request='Build Example for the simulator'
        env={'TYPESAFE_API_KEY':'sk-test-secret'}
        with patch.dict(os.environ,env), patch.object(system_one.urllib.request,'urlopen',
                return_value=FakeResponse(json.dumps(jev_reply()).encode())) as urlopen:
            result=routing.select(request)
        self.assertEqual((result.status,result.capability,result.model,result.confidence),('matched','build','jev-1.13.0',0.9))
        self.assertEqual(urlopen.call_count,1)
        sent=urlopen.call_args.args[0]
        self.assertEqual(sent.full_url,'https://api.typesafe.ai/v1/systemone')
        self.assertEqual(sent.get_header('Authorization'),'Bearer sk-test-secret')
        body=json.loads(sent.data)
        self.assertEqual(set(body),{'state','model','questions'})
        self.assertEqual((body['state'],body['model'],list(body['questions'])),({'request':request},'jev-latest',['capability']))
        asked=body['questions']['capability']
        self.assertEqual(asked['type'],'choice')
        self.assertEqual(asked['criteria'],dict(catalog.routing_options()))
        self.assertEqual(list(asked['criteria']),list(catalog.TOOLKIT_IDS))
        self.assertIn(catalog.testflight_extension()['policy'],asked['instructions'])
        for forbidden in ('projects.toml',str(natta.WORKSPACE_ROOT),str(Path.home()),'sk-test-secret'):
            self.assertNotIn(forbidden,json.dumps(body))
        self.assertNotIn('sk-test-secret',json.dumps(result.as_dict()))

    def test_jev_failure_never_falls_back_to_ollama(self):
        error=urllib.error.HTTPError('https://x',500,'err',{},io.BytesIO(b'PRIVATE'))
        with patch.dict(os.environ,{'TYPESAFE_API_KEY':'k'}), patch.object(system_one.urllib.request,'urlopen',side_effect=error) as urlopen:
            result=routing.select('Build Example')
        self.assertEqual((result.status,result.error,urlopen.call_count),('provider_error','provider_failure',1))
        self.assertEqual(urlopen.call_args.args[0].full_url,'https://api.typesafe.ai/v1/systemone')
        self.assertNotIn('PRIVATE',json.dumps(result.as_dict()))
        with patch.dict(os.environ,{},clear=False), patch.object(system_one.urllib.request,'urlopen',side_effect=AssertionError('network')):
            os.environ.pop('TYPESAFE_API_KEY',None)
            self.assertEqual(routing.select('Build Example').error,'credentials_missing')

    def test_ollama_backend_is_selected_by_configuration_only(self):
        reply={'message':{'role':'assistant','content':'{"choice":"F"}'}}
        with patch.dict(os.environ,{'NATTA_SYSTEM_ONE_BACKEND':'ollama','NATTA_OLLAMA_MODEL':'fixture:1b'}), \
             patch.object(system_one.urllib.request,'urlopen',return_value=FakeResponse(json.dumps(reply).encode())) as urlopen:
            result=routing.select('Build Example')
        # Without logprobs there is no confidence, so nothing passes the gate.
        self.assertEqual((result.status,result.reason,result.backend,result.model,result.confidence),
                         ('no_match','low_confidence','ollama','fixture:1b',None))
        self.assertEqual(urlopen.call_args.args[0].full_url,'http://127.0.0.1:11434/api/chat')
        self.assertEqual(json.loads(urlopen.call_args.args[0].data)['model'],'fixture:1b')

    def test_invalid_request_configuration_and_definitions_zero_model_calls(self):
        with s1fx.forbidden('model call'):
            self.assertEqual(routing.select(' ').status,'invalid_request')
            with patch.dict(os.environ,{'NATTA_SYSTEM_ONE_BACKEND':'codex'}):
                result=routing.select('request')
            self.assertEqual((result.status,result.error),('routing_error','provider_configuration_invalid'))
            with patch.object(catalog,'definitions',side_effect=ValueError('PRIVATE')):
                result=routing.select('request')
            self.assertEqual((result.status,result.error),('routing_error','definitions_invalid'))

    def test_no_evaluation_dependency_or_dispatch_and_frozen_definition_parity(self):
        for name in ('routing.py','semantic_catalog.py','system_one.py'):
            for node in ast.walk(ast.parse((natta.ROOT/name).read_text())):
                if isinstance(node,ast.Import): self.assertFalse(any(n.name in ('evaluate','local_model','execution','adapters','natta','subprocess','semantic_execution') for n in node.names))
                elif isinstance(node,ast.ImportFrom): self.assertNotIn(node.module,('execution','adapters','natta','subprocess'))
        self.assertEqual(catalog.DEFINITIONS.read_bytes(),(natta.ROOT.parent/'natta-local-model/evaluation/descriptions.json').read_bytes())
        with self.assertRaises(FrozenInstanceError): routing.RouteResult('matched','build').executed=True


class RouterDoctorTests(unittest.TestCase):
    def test_definitions_and_provider_rows_without_inference(self):
        with s1fx.forbidden('model call'), patch.object(system_one.urllib.request,'urlopen',side_effect=AssertionError('network')), \
             patch.dict(os.environ,{'TYPESAFE_API_KEY':'sk-secret'}):
            rows=routing.doctor_checks()
        self.assertTrue(all(ok for ok,_ in rows))
        self.assertEqual(rows[0][1],'Semantic definitions valid: 11 routing options, 8 planner capabilities')
        self.assertNotIn('sk-secret',json.dumps(rows))
        with patch.object(catalog,'definitions',side_effect=ValueError('PRIVATE')):
            self.assertEqual(routing.doctor_checks()[0],(False,'Semantic definitions invalid'))

    def test_doctor_no_provider_call_optional_core_health(self):
        out=io.StringIO()
        with s1fx.forbidden('model call'),patch.object(natta.local_model,'doctor_checks',return_value=[]), \
             patch.object(natta.shutil,'which',side_effect=lambda name:str(natta.WORKSPACE_ROOT/'bin/natta') if name=='natta' else '/fixture/tool'), \
             contextlib.redirect_stdout(out): self.assertEqual(natta.doctor([]),0)
        self.assertIn('OK  System One: backend=jev model=jev-latest min_confidence=0.50 (optional)',out.getvalue())
        self.assertIn('UNAVAILABLE  TypeSafe API key missing in TYPESAFE_API_KEY; service/auth not probed (optional)',out.getvalue())
        self.assertIn('Core Natta: ready',out.getvalue())
        with patch.object(routing,'doctor_checks',return_value=[(False,'Semantic router unavailable')]),patch.object(natta.local_model,'doctor_checks',return_value=[]), \
             patch.object(natta.shutil,'which',side_effect=lambda name:str(natta.WORKSPACE_ROOT/'bin/natta') if name=='natta' else '/fixture/tool'),contextlib.redirect_stdout(out): self.assertEqual(natta.doctor([]),0)
        self.assertIn('UNAVAILABLE  Semantic router unavailable',out.getvalue())


if __name__=='__main__': unittest.main()
