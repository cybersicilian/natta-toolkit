# Evaluation and extraction provenance

## System One provider change

The Codex CLI / `gpt-6-luna` provider was replaced by System One judgments
(TypeSafe Jev by default, or a configured Ollama model). Its router, planner
modules, sterile-workspace protocol, Codex evaluators/diagnostics
(`commit_evaluation.py`, `testflight_evaluation.py`, `planner_evaluation.py`,
`evaluate_codex.py`, `diagnose_codex.py`) and their tests were removed. The
regression suite uses mocked responses with no network access. Removed tests
covered only the Codex transport/evaluators; every execution, authorization,
confinement, commit and TestFlight safety test was kept, and routing/planning
tests were rewritten against mocked System One answers, including the
confidence gate and no-fallback behavior.

The published corpora and controls under `tools/natta/evaluation/` are kept
byte-identical (pinned by `public-controls-integrity.json`). Their controls hash
the old Codex prompts and schemas, so they are historical inputs, not System One
evidence. The default `min_confidence` of 0.5 is TypeSafe's documented
"genuinely uncertain" floor, not a threshold calibrated for Natta.

### Measuring System One

`tools/natta/evaluate_system_one.py` runs one public corpus against the
configured backend and never executes anything. It refuses unless
`--allow-external-requests` equals the exact request count, which is one per case
with Jev, and one per case for routing or nine per case for planning with Ollama.
It refuses an existing output file before any request. It asks with the gate
disabled, records each answer's confidence and probabilities, and derives the
outcome at every threshold from 0.00 to 0.95 offline. That gives exact accuracy,
coverage of positive cases, rejection of no_match cases and **unsafe accepts**
(resolved routes or plans that differ from gold) per threshold. Jev runs are
billed by TypeSafe.

```sh
cd tools/natta
python3 -B evaluate_system_one.py routing --corpus commit-routing-v2 \
  --allow-external-requests 16 --output "$PWD/evaluation/system-one-routing-commit-v2.json"
python3 -B evaluate_system_one.py planner --corpus planner \
  --allow-external-requests 36 --output "$PWD/evaluation/system-one-planner-v1.json"
```

Corpora: routing `commit-routing-v2`, `commit-routing-holdout-r1`,
`commit-routing-holdout-r2`, `testflight-routing-v1`; planner `planner`,
`commit-planner-v2`, `testflight-planner-v1`. Outputs match `*system-one*.json`
and are ignored by Git. The corpora are small (8–36 cases) and were written for
the old provider, so a threshold chosen from them is a starting point, not a
guarantee.

## Historical extraction

Historical record of the v1 extraction (not a current quality claim): the source
implementation's regression baseline was reported as 441 passed, 0 failed,
0 skipped, while static inventories of the source and the public derivative each
contained exactly 447 test methods. No test method was added or removed during
extraction, and all architectural safety contracts were retained. No source
application is needed by tests. Later public changes add their own tests; see the
README for the current suite.

Published evaluation definitions include core planner/commit/TestFlight corpora
and controls, and local-model selection corpus/descriptions/Phase 4C controls.
Fictitious project aliases/display names replace private application references.
The derivative's control hashes were recomputed for those sanitized inputs;
they are new public definitions, not byte-identical historical benchmark controls.
No production provider policy/domain was broadened by this operation.

Private host acceptance records, prompts/responses, model predictions, benchmark
results, fingerprints and machine/setup reports are excluded. No historical
benchmark accuracy is claimed for the rewritten public corpora. The original
research selected the current explicit semantic provider and rejected local
Qwen/OpenJEV routing; those decisions remain source history, not freshly measured
public-host certification.

Three tests in `test_model_profiles.py` previously loaded a historical 0.6B
benchmark. They now create complete synthetic 865-decision comparison data using
fake decisions, exercising input/model identity, summaries, comparison compatibility,
immutable-byte tampering and smoke-failure behavior. Synthetic data is generated
in disposable files and is not published as empirical model output.

`evaluate.py` and `evaluate_selection.py` retain explicit budgets and
non-execution boundaries. Real provider evaluation can cost money; no real
provider call was made during extraction validation. ML inference requires
explicit setup/MPS.

Historical `compare.py`, `run_comparison.py`, `run_selection_comparison.py` and
comparison helpers remain research-only code covered by tests. Their private
baseline artifacts are intentionally absent. The baseline digest is an explicit
unconfigured marker; comparison refuses until a reviewer supplies a new baseline
and pins its digest. The historical comparison runner additionally pins its
original stack versions and is not a general setup command. Use fresh evaluation
commands for public data; do not treat historical orchestration as production.

Confinement compatibility has no inherited source fingerprints. The current
manifest pins only the derivative's own implementation; a user must perform
host-local validation. No source validation receipt or model snapshot is shipped.

The full-metrics comparison test creates a synthetic baseline; the help-integrity
test protects a disposable repository instead of inspecting registered user
applications. The same validation, non-execution, tamper, metrics and integrity
contracts remain covered.

## Documentation map

Current normative contracts are TOOL_DESIGN, ROUTING, RESULT_CONTRACT,
EXECUTION_POLICY, EXECUTION_GATE, RUNTIME_EFFECTS, CONFINEMENT,
MACOS_CONFINEMENT, PLANNING, COMPOUND_EXECUTION, COMMIT and TESTFLIGHT under
`tools/natta/docs/`. Phase-labelled sections preserve design rationale and
historical domain evolution. Historical host narrative/results are excluded or
marked as source history. Current production planning uses System One
(`system-one-planner-v1`: status/context/diff/build/test/verify/commit/testflight).
Current behavior takes precedence over historical phase scope. `docs/ROADMAP.md`
contains future ideas only.

`public-controls-integrity.json` protects the exact published corpora and
controls bytes. Commit routing regression tests read those frozen corpora to check
that a commit selection still resolves projects locally.
