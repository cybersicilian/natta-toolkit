# Natta Toolkit

A deterministic-first, AI-assisted toolkit for explicit local development/workflow capabilities.

AI may select or plan from capabilities Natta explicitly knows about. Natta
validates that decision. Deterministic code performs the actual work.

Natta v1 is a small local control plane for registered repositories. Direct
commands work without AI. Optional semantic routing and bounded planning add a
convenience layer over the same handlers, policy and structured contracts.

## Architecture

```text
request
  → direct deterministic command OR bounded semantic decision
  → strict validation
  → deterministic argument/project resolution
  → policy evaluation
  → authorization where required
  → handler/confinement validation
  → deterministic execution
  → post-execution verification
  → structured result
```

This describes the semantic execution boundary. Direct commands retain their
command-specific validation and safeguards; they do not all pass through the
semantic gate. `route` stops at a proposed selection and `plan` stops at a
validated plan. Neither executes. Capability types are atomic (one focused
outcome), workflow (coordinated steps), and interface (a terminal/tool handoff).
Adapters implement mechanics; routing selects; workflows compose structured data.

Natta is not an autonomous agent system, arbitrary script runner, automatic plugin
discovery framework, MCP-first framework, or coding-agent harness. The `codex`
command hands off the terminal to a separately installed tool; Natta does not
implement that tool's behavior.

## Current v1 capabilities

| Command | Outcome |
| --- | --- |
| `projects` | List registered projects |
| `status PROJECT`, `context PROJECT` | Inspect identity, Git state, version and document paths |
| `diff PROJECT` | Inspect staged/unstaged change summaries without external diff tools |
| `doctor` | Required core health and separate optional readiness checks |
| `build PROJECT`, `test PROJECT` | Registered iOS/Xcode simulator workflows |
| `verify PROJECT --level 1\|2\|3` | Explicit adapter-defined verification profile |
| `commit PROJECT [--message TEXT]` | Stage all changes and make one local commit; never push |
| `testflight PROJECT --check` | Local-only readiness inspection |
| `testflight PROJECT [--confirm]` | Authorized signed archive/export and beta upload |
| `codex [PROJECT]` | Interactive Codex handoff at checkout root or registered repository |
| `route REQUEST` | One bounded System One capability selection; no execution |
| `execute [--confirm] REQUEST` | One validated semantic dispatch |
| `plan GOAL` | At most four linear intents, one System One call; no execution |
| `do [--confirm] GOAL` | Authorize a frozen plan, then sequential fail-fast dispatch |
| `confinement validate` | Explicit local inspection-backend validation with disposable fixtures |

`generic-git` supports inspection, local commit and Level 1 staged/unstaged
`git diff --check`. It does not infer Python build or test commands. `ios-xcode`
supports configured simulator build/test and verification levels; TestFlight uses
existing signing/account setup. TestFlight does not submit App Review, publish an
app, add testers, change versions or push Git state.

## Install

Currently supported/tested environment: **macOS**. Core requirements are Python
3.11+ and Git. No Python packages, virtual environment or model weights are
required for the core. See [dependency and compatibility details](docs/DEPENDENCIES.md).

From the root of a local checkout:

```sh
export PATH="$PWD/bin:$PATH"
natta --help
mkdir -p "$HOME/.config/natta"
cp examples/projects.toml "$HOME/.config/natta/projects.toml"
# Edit project paths and selections before running doctor.
natta doctor
```

Persist the checkout's absolute `bin` path in your shell's PATH configuration if
desired. Keep this wrapper in the checkout; copying it elsewhere changes its
relative source resolution. There is no installer, shell dependency, global
Python installation, automatic dependency repair or dependency on another checkout.

## Set up semantic commands (optional)

Direct commands need no AI. `route`, `execute`, `plan` and `do` need a System One
backend. Pick one.

**TypeSafe Jev (default).** Get an API key from [TypeSafe](https://docs.typesafe.ai)
and put it in the environment of the shell that runs `natta`. Natta reads only the
variable; it never stores or prints the key.

```sh
export TYPESAFE_API_KEY="..."        # or load it from your secret manager, e.g.
export TYPESAFE_API_KEY="$(gcloud secrets versions access latest --secret=typesafe-api-key)"
natta doctor                          # "TypeSafe API key present" (no request is made)
natta route --json "Verify Example App at level 1"   # one billed request, never executes
```

**Ollama (local).** Install [Ollama](https://ollama.com), pull a model, and select
it. Your Ollama server must return `logprobs` (0.35.1 does); without them no
answer has a confidence and nothing passes the gate.

```sh
ollama pull nimble
export NATTA_SYSTEM_ONE_BACKEND=ollama NATTA_OLLAMA_MODEL=nimble
natta doctor                          # "Ollama reachable" and "model nimble installed"
natta route --json "Verify Example App at level 1"
```

To keep the choice, copy [`examples/system_one.toml`](examples/system_one.toml) to
`~/.config/natta/system_one.toml`. Unknown keys or values fail closed. Check the
`confidence`, `probabilities` and `reason` fields of `--json` output; a
`reason` of `low_confidence` means the answer was below `min_confidence` and
nothing would execute. Semantic `status`/`context`/`diff` additionally need a
one-time `natta confinement validate` (see [confinement](tools/natta/docs/MACOS_CONFINEMENT.md)).
Full options: [System One configuration](tools/natta/docs/ROUTING.md#system-one-provider).

## Configuration and project registry

User configuration defaults to `~/.config/natta/projects.toml`. The global
`--registry PATH` option selects another file. No personal projects are shipped.
The [example registry](examples/projects.toml) is a template for fictitious
repositories, not a ready-made Xcode project or a promise that the paths exist.

```toml
schema_version = 1
[[projects]]
alias = "example"
aliases = ["example-app"]
name = "Example App"
path = "~/Projects/example"
type = "generic-git"
```

Each project must identify a Git repository root. Required fields are `alias`,
`name`, `path`, and `type`; aliases are globally unique lowercase letters/digits,
hyphens or underscores. `~` expands to your home directory. Relative project
paths resolve against the registry file's directory, not the calling shell.
Optional `agents`, `architecture`, `roadmap` and `version_source` paths must stay
inside the registered project. Unknown fields/schema versions fail closed.

For Xcode, `[projects.execution]` selects a project **or** workspace, scheme,
configuration and exact test targets/UI smoke identifiers. It accepts selections,
not executable shell text. See the [configuration walkthrough](examples/README.md)
and [capability design](tools/natta/docs/TOOL_DESIGN.md).

## Use

```sh
natta projects
natta status example
natta context example-app
natta diff example
natta verify example --level 1
natta --registry examples/projects.toml projects
natta route --json "Verify Example App at level 1"
natta plan --json "Inspect Example App and then verify it at level 1"
natta execute --confirm "Verify Example App at level 1"
```

Semantic commands ask **System One** questions: typed Choice judgments with
calibrated confidence, instead of a generative model used as a classifier.
Routing is one Choice over the capability IDs plus `no_match`. Planning is one
batched call that asks for scope, up to four ordered steps (or `stop`) and each
step's registered project. Project and verify parameters are resolved locally.
The default backend is [TypeSafe Jev](https://docs.typesafe.ai). Set
`TYPESAFE_API_KEY`, or select an Ollama-hosted model with
`NATTA_SYSTEM_ONE_BACKEND=ollama NATTA_OLLAMA_MODEL=<model>`. There is no
fallback between backends. An answer below `min_confidence` (default 0.5), or
one with no confidence, is a non-executing `no_match` with
`reason=low_confidence`. See the [System One configuration](tools/natta/docs/ROUTING.md#system-one-provider).

Request or goal text, capability descriptions and (for planning) project IDs,
aliases and display names are sent to TypeSafe over HTTPS, or to your configured
Ollama host. Repository paths, contents and diffs are never sent.
Natural-language wording never authorizes execution. Explicit policies require
invocation-local `--confirm` or affirmative terminal approval; JSON/non-TTY never
prompt. `do` authorizes the entire frozen plan before any prefix and reuses the
single-capability dispatcher. There is no autonomous replanning or rollback.

Direct `projects` and `doctor` are available. Semantic `projects` and `doctor`
intentionally remain unavailable because no validated confinement mode exists.
Semantic `status`, `context`, and `diff` require successful **local** macOS
inspection-confinement validation. No host receipt or inherited compatibility
authority is shipped. Read the [confinement contract](tools/natta/docs/MACOS_CONFINEMENT.md)
before running `natta confinement validate`. Build/test/verify, commit and
TestFlight use authorization and protected-state verification with the existing
unconfined workflow limits.

## JSON and diagnostics

```sh
natta doctor --json
natta plan --json "Inspect Example App"
natta commit unknown-project --json
natta testflight sample --check --json
```

Commands that support `--json` use their own structured success/failure envelopes,
including expected configuration and argument failures, with nonzero failure exit
codes. Inspection commands such as `status` use concise human output rather than
claiming universal JSON support. Programmer exceptions remain exceptions.
`no_match` is a valid non-executing selection, not an infrastructure success
substitute. [Result contracts](tools/natta/docs/RESULT_CONTRACT.md) define details.

`doctor --json` exposes `core_ready`, required Check-shaped rows and optional
System One/runtime/confinement/TestFlight rows (backend, model, API-key presence
never value, Ollama reachability). Missing optional components do not
fail core readiness. Doctor performs no model inference, build, signing or upload.

Workflow `--verbose` streams diagnostic output; `--log` explicitly retains logs
under `~/Library/Logs/NattaToolkit/`. Default temporary execution state is removed
on normal completion. Local models and validation records use
`~/Library/Application Support/NattaToolkit/`, separate from other installations.
No credentials belong in the registry. TestFlight credentials remain external.

## Trust and platform limits

The capability universe, strict provider protocol, handler/parameter/policy parity,
project identity checks and authorization bound supported execution. Model output
cannot become an arbitrary executable command through these routing contracts.
Protected-state snapshots detect observable violations and fail closed; they do
not roll back changes or prove the absence of network effects.

Semantic commands send bounded context to an external System One service (or
your Ollama host); restricted supplied context is not OS-enforced
confidentiality, and request text is sent as typed. Not every
deterministic workflow is sandboxed; trusted Xcode build phases/tests and other
third-party code can have ordinary host filesystem/network effects. Arbitrary
scripts are not inherently safe. See [the complete trust model](docs/SECURITY.md).

Natta names each repository explicitly; its Git commands never inherit ambient
`GIT_*` variables such as `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE` or
`GIT_CONFIG_*`. Protected operations (semantic execution, commit, TestFlight and
confinement validation) never run external Git clean/process filter programs, so
they refuse a repository with `external_filter_configured` only when a configured
filter actually applies to its files. Installing Git LFS globally does not block a
repository; a repository whose `.gitattributes` applies `filter=lfs` to tracked or
untracked, non-ignored files is refused by those protected operations.

Protected/workflow verification (direct build/test/verify, semantic execution,
commit and TestFlight) does not currently support repositories containing Git
submodules; such repositories are refused with `submodule_unsupported`
(`submodule_commit_unsupported` for commit). Direct `status`, `context` and `diff`
remain available.

Only macOS is supported/tested for v1. Native semantic inspection uses legacy
`sandbox-exec` and exact local validation; Xcode workflows and Apple services are
macOS-specific. Some stdlib/Git code is portable, but Linux/Windows are unvalidated
and not advertised as supported.

## Local-model status

The optional [isolated local-model research component](tools/natta-local-model/README.md)
returns bounded decisions as data and includes reproducible evaluation code.
It is experimental and does **not** replace the production System One provider.
Evaluated Qwen/OpenJEV selection quality was rejected for production routing.
No weights, downloaded caches, environments or external source projects are
redistributed. Setup/download are explicit optional actions.

## Test and extend

```sh
cd tools/natta
python3 -B -m unittest discover -s tests -v
```

The regression suite (459 tests at this revision) uses temporary repositories and mocked System One answers
and Apple commands. Historical-evidence-dependent tests construct synthetic
comparison data. If your Git config defines external filters (for example
git-lfs), commit tests fail closed by design. Run them with an isolated Git
configuration containing a test identity. Sanitized evaluation inputs
have public control hashes and are not represented as newly measured benchmarks.
See [evaluation provenance](docs/EVALUATION.md).

New capabilities require deliberate integration: deterministic implementation,
CLI registration, bounded metadata, parameter contracts, effect/policy declaration,
handler binding, protection/confinement where appropriate, result support and
regression tests. Automatic arbitrary-script discovery is intentionally absent.
The [extension walkthrough](docs/EXTENDING.md) annotates the existing mechanism.

## Status and roadmap

Natta Toolkit v1 is early software. What it guarantees is the architectural
contracts its regression suite enforces (strict validation, authorization, policy
recomputation, handler pinning, protected-state verification and fail-closed
confinement), not an absence of defects. The Python versions the suite has
actually run on are listed in [dependencies](docs/DEPENDENCIES.md); packaging is
not a public-host certification. Planning remains bounded/experimental;
local-model research remains optional.

The [roadmap](docs/ROADMAP.md) separates present behavior from possible future
work. Broader platforms, new capabilities and stronger isolation would need
separate design and validation; none are promised or implemented by extraction.

## License

Natta Toolkit is released under the [MIT License](LICENSE).

Copyright (c) 2026 Juan Desiderio Verano Mesa

Third-party components retain their respective licenses. See
[third-party provenance](docs/PROVENANCE.md) and
[dependency documentation](docs/DEPENDENCIES.md) for additional details.
