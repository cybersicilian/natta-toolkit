"""Bounded semantic capability universe. No provider, handler or dispatch API.

Routing and planning ask System One questions whose options come only from here.
Integrity checks keep CLI registrations, frozen routing descriptions and the
reviewed commit/TestFlight extensions in sync; any drift fails closed.
"""
import ast
import json
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
DEFINITIONS = SOURCE / 'config/routing.json'
ROUTING_IDS = ('projects', 'status', 'context', 'diff', 'doctor', 'build', 'test', 'verify', 'no_match')
PRODUCTION_IDS = (*ROUTING_IDS[:-1], 'commit', 'no_match')  # historical commit controls
TOOLKIT_IDS = (*PRODUCTION_IDS[:-1], 'testflight', 'no_match')
# CLI commands that are never semantic targets: route is the selector itself and
# codex is an interactive terminal handoff, not a bounded capability.
NON_TARGETS = frozenset(('codex', 'route'))
PLANNER_IDS = ('status', 'context', 'diff', 'build', 'test', 'verify', 'commit', 'testflight')
MAX_STEPS = 4


def authoritative_ids():
    """Read CLI registration syntax without importing executable handlers."""
    tree = ast.parse((SOURCE / 'natta.py').read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'make_parser')
    assignment = next(n for n in function.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'pages' for t in n.targets))
    return frozenset(ast.literal_eval(assignment.value))


def executable_ids():
    return authoritative_ids() - NON_TARGETS


def definitions():
    data = json.loads(DEFINITIONS.read_text())
    ids = executable_ids()
    if ids not in (set(ROUTING_IDS)-{'no_match'},set(PRODUCTION_IDS)-{'no_match'},set(TOOLKIT_IDS)-{'no_match'}):
        raise ValueError('Routing universe differs from real CLI registrations')
    if not isinstance(data, dict) or set(data) != {'schema_version', 'concise', 'precise'} or data['schema_version'] != 1:
        raise ValueError('Unknown description schema')
    for name in ('concise', 'precise'):
        values = data[name]
        if not isinstance(values, dict) or set(values) != set(ROUTING_IDS) or any(not isinstance(v, str) or not v for v in values.values()):
            raise ValueError('Frozen descriptions differ from real CLI registrations')
    return data


def production_definitions(*, routing_revision=False):
    data=definitions()
    extension=json.loads((SOURCE/'config/routing-commit-v2.json').read_text())
    if (set(extension)!={'schema_version','capability','description','routing_description'} or extension['schema_version']!=2
            or extension['capability']!='commit' or not isinstance(extension['description'],str)
            or not extension['description'] or not isinstance(extension['routing_description'],str)
            or not extension['routing_description'] or executable_ids() not in
                (set(PRODUCTION_IDS)-{'no_match'},set(TOOLKIT_IDS)-{'no_match'})):
        raise ValueError('Invalid reviewed routing extension')
    # Planning keeps the accepted commit description; routing uses its own revision.
    description=extension['routing_description' if routing_revision else 'description']
    return {**data, **{name:{**data[name],'commit':description} for name in ('concise','precise')}}


def testflight_extension():
    extension=json.loads((SOURCE/'config/routing-testflight-v1.json').read_text())
    if (set(extension)!={'schema_version','capability','description','policy'}
            or extension['schema_version']!=1 or extension['capability']!='testflight'
            or any(not isinstance(extension[k],str) or not extension[k] for k in ('description','policy'))
            or executable_ids()!=set(TOOLKIT_IDS)-{'no_match'}):
        raise ValueError('Invalid TestFlight extension')
    return extension


def toolkit_definitions(*, routing_revision=False):
    data=production_definitions(routing_revision=routing_revision)
    extension=testflight_extension()
    return {**data, **{name:{**data[name],'testflight':extension['description']} for name in ('concise','precise')}}


def routing_options():
    """Ordered (id, description) pairs for the one routing Choice question."""
    values = toolkit_definitions(routing_revision=True)['concise']
    return tuple((name, values[name]) for name in TOOLKIT_IDS)


def planner_options():
    """Ordered (id, description) pairs for planner step questions, without stop."""
    if not set(PLANNER_IDS) <= executable_ids():
        raise ValueError('Planner domain differs from real CLI registrations')
    values = toolkit_definitions()['concise']
    return tuple((name, values[name]) for name in PLANNER_IDS)
