# Implemented trust model

Natta v1 uses explicit capabilities, not arbitrary command generation. The
semantic selector/planner asks System One Choice questions whose options Natta
supplies; an answer is only one option ID from that set, plus probabilities and a
confidence. Strict response validation rejects unknown or missing questions,
choices outside the option set, duplicate keys, malformed probabilities and
unexpected response shapes. Model output has no supported arbitrary-command,
path, flag or argument path. Answers below `min_confidence` (default 0.5), or
without any confidence, become a non-executing `no_match` (`low_confidence`).

## What leaves the machine

Semantic commands (`route`, `execute`, `plan`, `do`) send data to the configured
System One backend; direct commands send nothing.

- **TypeSafe Jev (default):** HTTPS `POST https://api.typesafe.ai/v1/systemone`
  with a bearer key read from `TYPESAFE_API_KEY`. TypeSafe receives the
  natural-language request or goal, Natta's fixed instructions, the routing/planner
  capability descriptions and, for planning, registered project IDs, aliases and
  display names. TypeSafe's own data handling applies; see
  [its legal documentation](https://docs.typesafe.ai/legal).
- **Ollama (opt-in):** the same questions go to the configured Ollama host over
  HTTP. The default `http://127.0.0.1:11434` stays local; a remote host receives
  the same content, unencrypted unless you configure an `https://` host.

Natta never sends repository paths or contents, diffs, documents, registry paths,
environment values or credentials other than the TypeSafe bearer key. The key is
never written to a file, printed or included in results. There is no fallback
between backends and no retry beyond bounded Jev HTTP 429/529 backoff.

Before semantic dispatch, Natta validates CLI/catalog/parameter/binding/policy
parity, resolves project/arguments deterministically, revalidates identity and
authorization, and applies the existing protection requirements. Selection and
policy eligibility do not authorize execution. Explicit policies require terminal
approval or invocation-local `--confirm`; JSON/non-TTY cannot prompt. Compound
execution freezes at most four linear steps, authorizes the whole plan before
execution, pins targets and fails fast. No retries, replanning or rollback.

Semantic inspection (`status/context/diff`) requires exact host-local validation
of the macOS inspection backend. The deny-default sandbox profile allows broad
reads/processes but denies network and filesystem writes outside its owned
runtime (with `/dev/null` allowed). It is write/network confinement, not read
confidentiality. The public compatibility list starts empty and ships no receipt.
Semantic `projects` and `doctor` fail closed because they have no validated mode.
Direct commands remain available and do not all run inside this sandbox.

Build/test/verify, local commit and TestFlight enforce their declared authorization
and protected-state verification, without native workflow confinement. Snapshot
comparison checks observable project content/Git effects. Commit permits the
reviewed index/HEAD mutation while rejecting unrelated protected changes.
TestFlight declares its Apple-network effects and keeps credentials external.
Verification failure or unavailable required protection is not reported as success.

Git commands run against the registered repository path with ambient `GIT_*`
variables removed, so `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_CONFIG_*`
and similar routing cannot redirect inspection, snapshots or commits. Protected
snapshots and the direct build/test/verify integrity snapshot read attributes
with `git check-attr` and refuse
(`external_filter_configured`) only when a configured clean/process filter applies
to a tracked or non-ignored untracked file; Natta never executes that filter. A
configured but unused filter, such as a global Git LFS installation in a
repository without `filter=lfs` attributes, does not affect availability.
Protected/workflow verification does not currently support repositories
containing Git submodules: any submodule (gitlink) in the index is refused with
`submodule_unsupported` (`submodule_commit_unsupported` for commit), read from the
index alone before any Git command could recurse into it or run a filter
configured inside it. Direct `status`, `context` and `diff` are ordinary Git
inspection and are not covered by this refusal.

## Non-guarantees

- Request/goal text is sent as typed. If it contains secrets or private names, the
  configured backend receives them. Natta does not redact request text.
- Natta does not authenticate the Ollama host beyond the URL you configure, and
  calibrated confidence is a statistic, not proof that a selection is correct.
- Bounded intentionally supplied context is not OS-enforced confidentiality.
- Trusted Xcode phases/tests and other third-party code can write elsewhere or use
  network/external services. Policy-denied effects are not all actively prevented.
- Arbitrary third-party scripts are not safe by default. Registry shell code is not
  evaluated and arbitrary scripts are not drop-in capabilities.
- Post-execution verification is detection within observable scope. It is not proof
  of no external effects, a rollback engine, credential secrecy or malware isolation.
- A successful TestFlight upload is not remote processing completion or public release.

Read [routing](../tools/natta/docs/ROUTING.md),
[execution gate](../tools/natta/docs/EXECUTION_GATE.md),
[confinement](../tools/natta/docs/MACOS_CONFINEMENT.md), and
[runtime effects](../tools/natta/docs/RUNTIME_EFFECTS.md) for normative contracts.
