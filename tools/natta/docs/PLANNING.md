> Standalone v1: current contracts are preserved below. Phase-labelled sections
> record historical domains/rationale; private empirical artifacts are excluded.
> See [documentation map and evaluation provenance](../../../docs/EVALUATION.md).

> Current Phase 8B addition: optional `natta do` executes a frozen bounded plan.
> Earlier statements below that compound execution is absent describe pre-8B scope.
> `route`, `execute` and `plan` retain their existing boundaries; direct CLI remains
> primary. See [compound execution contract](COMPOUND_EXECUTION.md).

# Current planner: system-one-planner-v1

`natta plan [--json] GOAL` proposes an experimental linear plan of one to four
steps and never executes. `do` reuses it, then authorizes and dispatches the
frozen plan (see [COMPOUND_EXECUTION.md](COMPOUND_EXECUTION.md)). The permitted
capabilities are status/context/diff/build/test/verify/commit/testflight;
projects/doctor stay excluded. Commit and TestFlight keep their whole-goal
rejection rules (see [COMMIT.md](COMMIT.md) and [TESTFLIGHT.md](TESTFLIGHT.md)).

## One batched System One call

Each goal makes exactly one System One call. That is one HTTP request with Jev,
or one request per question (nine) with Ollama. There are no retries beyond
bounded Jev 429/529 backoff, no fallback and no per-step routing. The state is
`{"goal": TEXT}` and the questions are fixed:

| Question | Options | Meaning |
| --- | --- | --- |
| `scope` | `supported`, `unsupported` | Can the **whole** goal be done with the listed capabilities in at most four steps? Any other operation, such as push, a custom commit message or public release, makes it unsupported. A prefix is never accepted. |
| `step_1`..`step_4` | the eight planner capabilities, `stop` | The capability for step *k*, in stated order with explicit repeats, or `stop` if there are fewer than *k* steps. |
| `project_1`..`project_4` | registered aliases, `unspecified` | The registered project step *k* acts on. Each option is described by display name and aliases only. |

Answers are converted to a candidate and then pass through the **unchanged**
local validation described below (registry, argparse schema, policy, handler
binding). Conversion fails closed:

- A `stop` must be followed only by `stop`; otherwise `invalid_plan`/`malformed_plan`.
  `step_1=stop` is `no_match`.
- `scope=unsupported` is `no_match` with `reason=unsupported_goal`.
- `unspecified` for a real step is `no_match` with `reason=project_unspecified`.
  A chosen project must also be named in the goal text (alias, registered alias
  or display name, matched as in route resolution, so pronouns like "it" resolve
  to a project the goal names). Otherwise the result is
  `invalid_plan`/`unknown_project` with `invalid_step`.
- Verify levels are **not** asked. They come from explicit `level N` text in the
  goal via `parameters.py`. A verify step without one is `no_match` with
  `reason=level_missing`. Invalid or conflicting distinct levels are
  `invalid_plan`/`invalid_argument`. One explicit level therefore applies to
  every verify step of the goal.
- The local public-release veto still turns a public App Store goal into `no_match`.

### Confidence gate

Every deciding answer (scope, the step answers up to and including the first
`stop`, and the project answers of real steps) must reach `min_confidence`
(default 0.5) and must carry a confidence. Otherwise the result is `no_match`
with `reason=low_confidence` and zero steps, so `do` executes nothing even with
`--confirm`. Answers after the closing `stop` do not decide the plan.

### Result additions

PlanResult keeps every field and status described below. It now reports
`provider="system-one"`, `planner_version="system-one-planner-v1"`, `backend`,
`model`, `min_confidence`, `reason` (null or one of `low_confidence`,
`unsupported_goal`, `project_unspecified`, `level_missing` on `no_match`) and
`answers`: for each question, `choice`, `probabilities` (or null) and
`confidence` (or null). `external_requests` counts System One HTTP requests.
Provider failures are `provider_error` with bounded codes shared with routing
(credentials_missing, provider_unavailable, provider_timeout, rate_limited,
overloaded, provider_failure, malformed_output, provider_configuration_invalid).

### What is sent

The goal, Natta's fixed instructions, the planner capability descriptions and
registered project IDs, aliases and display names. No repository paths,
contents, execution configuration, diffs or documents are sent. The data goes to
TypeSafe over HTTPS by default, or to the configured Ollama host. See
[the trust model](../../../docs/SECURITY.md).

### Known narrowing

Because levels are resolved from the whole goal, a plan that needs two different
verify levels, such as "verify Example at level 1 and Sample at level 2", fails
closed as `invalid_argument` instead of being planned. None of the public planner
corpora contain such a case. System One planning accuracy has not been measured on
those corpora; see [evaluation provenance](../../../docs/EVALUATION.md).

# Historical Phase 8A v1 contract (superseded domain/provider)

`natta plan GOAL` and `natta plan --json GOAL` propose an experimental linear plan.
They never execute a step. `route` continues to report one capability; `execute`
continues to authorize and execute one capability through its existing gate.
In this historical Phase 8A scope, do was not implemented; current bounded do is documented separately. No confirmation flag exists on plan.

## Separate provider mode (removed)

The historical Phase 8A planner used a separate Codex/`gpt-6-luna` workspace and
prompt. That provider and its evaluator were removed. The structural contract
below (local validation, immutable result) is unchanged and is what
`system-one-planner-v1` answers are validated against.

## Local validation

A plan contains **one to four** ordered steps from status, context, diff, build,
test and verify. Projects/doctor are excluded initially. no_match is an overall
outcome with zero steps; it is never a step. Unsupported or mutating goals must
be rejected in their entirety, including unsupported parts of an otherwise safe
goal. Plans over four steps are rejected, never truncated. Duplicates are preserved
in explicit order. No optimizer, DAG, loops, conditions, branching, parallelism,
retries or dynamic replanning exists.

The v1 validator validated each untrusted proposal against (current production
uses the additive eight-capability domain):

- authoritative executable CLI IDs and the six-capability planning subset;
- current project registry ID, aliases or display name, matched as a complete
  Unicode-normalized, case-insensitive reference; exactly one canonical ID must match;
- existing argparse-derived parameter requirements: all six require a project;
  verify requires an exact integer level 1, 2 or 3, other arguments must be empty;
- authoritative policy integrity, eligibility, authorization enum and denied effects;
- callable presence in the static handler binding catalog, without invoking it.

Unknown/ambiguous projects, paths, arbitrary flags, bool/string/float levels,
missing or extra arguments, unknown capabilities and forbidden policy invalidate
**the whole plan**. No partially validated steps or summaries are returned.
Raw goal text never reaches a handler. Local validation proves structural bounds;
it does not prove that a bounded plan faithfully represents every part of a goal.
For example, the model could omit a forbidden part and propose only a build. The
separate adversarial/unsupported evaluation measures that semantic rejection.
Nothing executes even if a locally valid but semantically incorrect plan appears.

Authorization is automatic only when every step is automatic, otherwise explicit.
It is informational and consumes no authorization. The effect union is computed
from local policy. Inspection steps report confinement required, never applied;
workflows report no native confinement requirement. Each project-targeted step
reports runtime_verification_required=true. These describe future requirements,
not current host readiness or authorization to dispatch. No host validation,
project inspection, runtime snapshot, sandbox application or Xcode invocation
occurs during planning. Policies retain denied network/project/Git mutation; the
accepted workflow residual risks remain as documented in EXECUTION_GATE.md.

## Immutable result and output

PlanResult and Step are frozen structures; arguments are immutable tuples and
effects a frozenset. JSON exposes status, valid, provider, planner_version,
experimental=true, executed=false, steps, authorization/effects, error,
invalid_step, confinement summary, external_requests and inference_seconds.
Each step includes canonical project, bounded arguments, arguments_resolved=true,
execution_policy, authorization, confinement and runtime-verification requirement.
Every step also has executed=false.

Statuses:

| Status | valid | Steps | Exit |
| --- | --- | --- | --- |
| planned | true | All validated steps | 0 |
| no_match | false | Empty | 0 |
| invalid_plan | false | Empty | 1 |
| invalid_request | false | Empty | 1 |
| provider_error | false | Empty | 1 |

no_match means there is no executable plan, not a failed provider. Bounded local
errors include unknown_capability, unsupported_capability, unknown_project,
ambiguous_project, invalid_argument, too_many_steps, forbidden_step,
missing_handler, malformed_plan and planner_configuration_invalid. Provider and
configuration failures remain distinct. Malformed structured output invalidates
the plan and counts as a provider/output failure in evaluation. No unsafe proposed
fields or reasoning appear in error results. Human output prints ordered steps,
optional level, authorization, executed=no and experimental=yes. JSON stdout
contains one JSON object, without diagnostic prose.

## Frozen compact evaluation

`evaluation/planner-corpus-v1.json` contains 36 manually declared cases, created
before any real planner run. Allocation: two-step 8, three-step 3, four-step 1,
project variation 4, verify levels 4, reordered wording 3, ambiguous/invented
projects 3, unsupported mutation 4, adversarial injection 3, explicit duplicate 1,
single-step 1, over-complexity 1. Expected results are canonical ordered plans or
whole-goal no_match. No Phase 4D data or provider output selected these cases.

`planner-controls-v1.json` freezes corpus, planner prompt, policy, schema and
capability/project-metadata hashes. Changes refuse the evaluation. Predeclared
acceptance requires all 36 completed, zero provider/infrastructure/output failures,
at least 90% exact-plan accuracy (**33/36**), 100% rejection of all four unsupported
and all three adversarial cases, and zero accepted unknown capabilities/projects.
These gates must not be changed after results. Failure leaves planning experimental;
passing does not enable compound execution.

The evaluator reports exact-plan, capability-sequence, project and argument
accuracy, unsupported/adversarial rejection, provider failures, incorrect cases,
request counts and new-call timing. Projection metrics compare entire ordered
sequences and require matching overall status; they are descriptive, never a
substitute for exact-plan acceptance. Rejected unsafe invalid proposals can count
as safe rejection but do not count as exact gold no_match. Every frozen case is in
the denominator. No retries or hidden extra model requests occur. Smoke uses the
first frozen case once; evaluation uses all 36 in frozen file order. Both outputs
are exclusive private new files; existing artifacts refuse before provider use.
Interrupted runs save incomplete evidence and never pass acceptance.

The Codex-specific runner for this frozen evaluation (`planner_evaluation.py`) was
removed with the provider. The corpus and controls remain byte-identical as
historical inputs; their controls hash the removed Codex prompt and schema.

## TestFlight extension

The direct `natta testflight PROJECT` product capability now archives and uploads
beta builds using Apple's supported Xcode distribution tooling. Its explicit
network/external-service policy is specific to TestFlight; source/Git writes stay
denied. Route/execute and bounded plan/do include the additive capability, using
one approval and existing per-step verification. Historical provider controls and
historical provider domains remain represented by public definitions. App Store public release is not implemented. Read the
[TestFlight contract](TESTFLIGHT.md) for exact prerequisites, results and boundaries.
