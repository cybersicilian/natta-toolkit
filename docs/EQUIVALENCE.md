# Source architecture equivalence

The derivative preserves the verified source v1 architecture. These are extraction
transformations, not new provider, policy, executor or capability architecture.
The one later exception is the semantic provider: the source Codex/gpt-6-luna
provider was removed and replaced by System One (TypeSafe Jev by default, or a
configured Ollama model) behind the same local validation.

| Personal v1 component | Open-source component | Change |
| --- | --- | --- |
| Managed shell launcher | `bin/natta` | packaging-only; checkout-relative stdlib wrapper |
| Project registry | `~/.config/natta/projects.toml`, `examples/projects.toml` | path/config generalized; schema unchanged, fictitious mappings |
| CLI | `tools/natta/natta.py` | path/config generalized; public help sanitized |
| Routing | `routing.py`, routing configuration JSON | unchanged |
| Provider boundary | `system_one.py`, `semantic_catalog.py` | replaced: Codex `router_codex.py` removed; capability-universe integrity checks moved unchanged |
| Parameters | `parameters.py` | unchanged |
| Policy | `policy.py` | unchanged |
| Authorization | `authorization.py` | unchanged |
| Semantic execution | `semantic_execution.py` | unchanged |
| Deterministic adapters | `adapters.py`, `execution.py`, `commits.py`, `testflight.py` | log path generalized; execution logic unchanged |
| Confinement | `confinement.py`, `macos_confinement.py`, worker and manifest | path/config generalized; inherited compatibility hashes intentionally omitted |
| Runtime verification | `runtime_effects.py` | unchanged |
| Planning | `planning.py` | Codex planner providers v1/v2/v3 removed; System One planner; local validation unchanged |
| Compound execution | `compound_execution.py` | unchanged |
| Result handling | existing dataclasses/renderers/JSON envelopes | unchanged |
| Doctor | CLI health checks | launcher path generalized; required/optional readiness unchanged |
| Local-model component | `tools/natta-local-model`, `local_model.py` | sanitized; model state path generalized, no environments/weights/host outputs |
| Tests | all source test modules | sanitized fixtures/path expectations; private-evidence tests use synthetic data |
| Docs | normative `tools/natta/docs`, standalone docs | sanitized; obsolete/private host evidence intentionally omitted |

The isolated runtime namespace prevents public logging/confinement
state from colliding with another installation; System One launches no provider
subprocess and keeps no routing/planning workspace. The default registry is outside
source so user mappings need not enter Git. The confinement manifest has no prior
implementation entries or host receipt: packaging edits cannot inherit trusted
host validation. This strengthens fresh-install fail-closed availability without
changing the existing backend or protection model. Bare `codex` launches the
toolkit checkout root; project launches still use registry lookup. No capability
universe, validation rule, authorization rule or result status was broadened.

Historical research comparison helpers cannot use excluded private results. They
fail until a reviewed baseline exists; unit tests use explicit fake data. Public
control hashes identify sanitized definitions, not remeasured model accuracy.
