# Dependencies and platform compatibility

## Core and development

Python 3.11+ (uses `tomllib`, modern type syntax and pathlib methods), standard
library only. Tests use `unittest` and disposable Git repositories. No pip packages
are needed. Git must support `--no-optional-locks`, porcelain v1 `-z`, root/branch
inspection, diff checks, local plumbing and the config flags used by commits.
The extraction validation records exact installed versions in the review report;
command presence alone is not a compatibility guarantee. No fabricated Git/Xcode
minimum version is claimed.

The POSIX `bin/natta` wrapper requires `sh`, `dirname`, and `python3` on PATH.
Its source paths resolve within this checkout. No dotfiles, shell aliases or global
site-package installation is required.

## Optional semantic provider

`route`, `execute`, `plan` and `do` use a System One provider through the Python
standard library (`urllib`); no SDK or package is installed.

- **TypeSafe Jev (default):** network access to `https://api.typesafe.ai` and a
  TypeSafe API key in `TYPESAFE_API_KEY`. Calls are billed per input token by
  TypeSafe. `jev-latest` is an alias that can move to a new model version; pin a
  versioned ID (for example `NATTA_JEV_MODEL=jev-1.13.0`) if you tune thresholds.
- **Ollama (opt-in):** a running Ollama server and a pulled model, selected with
  `NATTA_SYSTEM_ONE_BACKEND=ollama` and `NATTA_OLLAMA_MODEL`. The server must
  return `logprobs` for `/api/chat`, or no answer has a confidence and nothing
  passes the confidence gate. No minimum Ollama version is claimed; check with a
  smoke request.

Configuration is optional: `~/.config/natta/system_one.toml` and `NATTA_SYSTEM_ONE_*`
environment overrides, both validated strictly. See
[the routing contract](../tools/natta/docs/ROUTING.md#system-one-provider).
Doctor reports configuration, key presence and Ollama reachability without
inference. Missing credentials or an unreachable backend fail closed and leave
direct commands usable.

The separate `natta codex` command launches an installed Codex CLI as an
interactive terminal handoff. It is not a semantic provider.

## macOS, Xcode and Apple

Only macOS is supported/tested for v1. Native semantic inspection requires
`/usr/bin/sandbox-exec`, `/usr/bin/sw_vers`, `/usr/bin/git`, a compatible interpreter
and exact successful host-local fixture validation. Legacy sandbox availability is
not assumed. Other OSes are not supported despite portable portions of Python/Git.

Xcode-specific workflows require selected command-line tools, `xcodebuild`,
`xcrun`, an available compatible iOS Simulator runtime, and configured schemes/
targets. Level 3 uses `plutil` for Git-visible Apple metadata syntax. External
DerivedData/package/result directories are used; automatic package resolution is
disabled. Required package setup is deliberate work outside Natta.
`xcresulttool get test-results summary` JSON supplies best-effort test counts;
older/incompatible versions provide no invented counts. Exit/check results remain
authoritative. Native build/test/upload compatibility was not rerun on real apps
for extraction: the full suite mocks Apple commands.

TestFlight also invokes the macOS `security find-identity` probe for local
signing identity inspection; it never exports private keys.

TestFlight additionally needs a suitable Apple Developer team, bundle/version/build
metadata, signing/provisioning and App Store Connect access via existing Xcode
account or externally configured API-key authentication. `testflight --check` and
doctor remain local-only and do not establish remote-service readiness. No
credentials, account/signing artifacts or API keys are distributed. See
[the exact release prerequisites](../tools/natta/docs/TESTFLIGHT.md).

## Optional local-model research

Separate Python 3.12 (`>=3.12,<3.13`), an already installed uv-managed interpreter,
`uv`, Apple Silicon/MPS and explicit network-enabled setup. The isolated manifest
pins OpenJEV's source commit and requires torch >=2.0, transformers >=4.51.0 and
huggingface-hub. `uv.lock` pins resolved direct/transitive dependencies; it is kept
without environments or vendored sources. Transformers' Qwen3 floor is intentional.
MPS/FP32/offline inference is validated at runtime with no CPU/cloud fallback.
The source stack is not claimed compatible with every later package/hardware
version. Ordinary Natta commands never install/download/load these packages.
