# `rb` CLI and Experiment Authoring

**Status:** Accepted
**Date:** 2026-08-23

## Objective

Ralph Bench should be approachable as a guided terminal application and remain
reproducible as a declarative command-line tool. The installed executable is
`rb`, short for Ralph Bench.

Running `rb` with no arguments starts an interactive experiment wizard. The
wizard discovers what it safely can, explains where each choice came from,
uses intelligent but visible defaults, writes a validated TOML experiment,
and offers to run it. The saved TOML—not wizard memory—is the reproducible
input to the conductor.

The wizard authors normalized intent; it does not directly edit provider or
client-native configuration. Runtime materialization follows the centralized
ownership and rollback contract in
[`CONFIGURATION_MODEL.md`](CONFIGURATION_MODEL.md).

Explicit commands remain available for automation and exact reruns:

```bash
rb
rb configure
rb configure experiments/cloud-intersection.toml
rb run experiments/cloud-intersection.toml
rb bundle validate results/inbox/<run-id>.ralph.zip
rb build --source results/inbox --output site
```

`rb run` requires an experiment path. The zero-argument `rb` command enters the
wizard; in a non-interactive environment, commands that need answers fail with
an actionable message rather than guessing.

## Vocabulary

The user-facing term is **client**: Codex CLI, OpenCode, Gemini CLI, or another
agentic coding application. Internally, a client is represented by a
`HarnessAdapter`. The experiment format uses `client` because that is the
operator's choice; the core uses harness to distinguish it from API clients.

Harnesses, providers, and models are independently registered and composed by
the capability resolver described in [`ADAPTER_MODEL.md`](ADAPTER_MODEL.md).
The wizard consumes the same registry and must not maintain its own vendor
catalog or compatibility branches.

The system under test remains the complete combination:

```text
client x model x provider/configuration x effort/tool policy
```

## Zero-argument flow

The first substantive question is always the client. The current P0-A flow
implements client/provider/model discovery, challenge, effort, repetition,
wall-time, repair-pass, inbox, save, and post-save run confirmation. An
operator-facing isolation choice and back/edit navigation remain later UI
work:

1. **Client** — show detected compatible clients, executable paths, versions,
   and detection status.
2. **Provider** — show providers supported or configured for that client,
   separated into local and cloud choices.
3. **Model** — query the selected client/provider where possible and show model
   IDs with the source and freshness of the discovery.
4. **Challenge** — Busy Intersection is the primary current challenge. The
   Challenge Portability Fixture is an internal seam proof, not a competing
   city choice; future city challenges remain open for later extension.
5. **Client and model controls** — reasoning/effort, tool policy, native versus
   controlled loop, and adapter-specific supported options. Controlled
   execution is the current Codex path. Pi-wiggum is the explicitly approved
   next native-loop implementation; it remains distinct from Ralph's
   evaluator-controlled repair loop.
6. **Experiment basics** — ask for a concise experiment name, repetitions as
   **Independent runs per configuration**, explain that they are aggregated
   to measure variability, and collect a per-run wall-time ceiling.
7. **Repair policy** — offer **Ralph repair passes** as the evaluator-controlled
   repair loop, separately from the independent repetition runs.
8. **Scenario and isolation** — derive the scenario profile from the selected
   challenge and track through the shared challenge/profile registry and show
   the resulting profile. The current P0 path uses portable L0/unsealed
   staging; an operator-facing isolation choice remains future UI work. The
   user should not have to invent a scenario-pack ID for the common path.
9. **Result inbox** — explain that the inbox is the local destination for
   immutable `.ralph.zip` evidence and suggest a safe path; do not imply that
   it is a live report or a cloud upload.
10. **Review** — render the complete TOML before saving. Provenance-rich
    defaults and move-back editing remain later wizard work.
11. **Validate and save** — use one path prompt with a filename derived from
   the experiment name, write atomically, never silently overwrite, and report
   the exact path. Entering the path is the save confirmation; do not ask a
   redundant yes/no question first.
12. **Run** — offer to execute the saved experiment. The default-yes prompt
    states the number of independent runs and maximum possible model
    invocations. Declining leaves the TOML ready for `rb run`; confirming calls
    the same conductor as the explicit command. Cloud runs explain the
    available billing/reference evidence; P0-A subscription runs do not show a
    cost questionnaire or request a synthetic allocation.

The interface should support Enter to accept a displayed default, numbered
choices, back, help, manual entry, and quit without leaving a partial file.
Terminal polish is welcome, but correctness, accessibility, and testability
take priority over a dependency-heavy UI.

## Intelligent defaults

Defaults are suggestions, not hidden inputs. Every proposed value is displayed
before acceptance. The preference order is:

1. A compatible value already present when completing an existing TOML file.
2. The most recent successful choice recorded in local, non-secret UI state,
   if it is still detected and compatible.
3. A currently active or uniquely detected client/provider/model. For a
   harness with an update-aware adapter, the current release is checked before
   execution and the exact release used is recorded in provenance.
4. A challenge- or adapter-defined safe default.
5. No default; require a choice.

Remembered UI state may accelerate authoring but must never affect execution of
an already saved experiment. Environment-derived values are resolved into the
TOML or recorded as explicit runtime references. The final review identifies
which values were selected, inferred, or entered manually.

Defaults must be cost-aware. Discovery does not send a generation request.
Selecting a cloud provider does not authorize a run. Missing cost must not be
presented as zero. In P0-A, a subscription selection is valid without a
financial questionnaire; the resulting bundle says cost is unavailable and
preserves time, token, and attempt evidence.

## Discovery contract

Discovery is capability-based rather than a promise that every client has a
provider/model listing command. P0 should define structured probe results for:

- Client presence, executable path, version, and basic health.
- Supported or configured providers.
- Available model identifiers and optional metadata.
- Supported reasoning/effort modes and loop behavior.
- Credential availability as a boolean or named profile, never a secret.
- Discovery source, timestamp, warnings, and confidence.

The probe order is:

1. A selected adapter's documented, read-only discovery command or API.
2. A provider's documented model-list endpoint, scoped through the selected
   client configuration where necessary.
3. Read-only inspection of the client's relevant configuration references.
4. A recent cached discovery result, clearly labeled stale and revalidated
   where possible.
5. Manual provider, endpoint, and model entry.

Choices should be the compatible intersection of client and provider
capabilities, not an unfiltered global model catalog. A model discovered from
an endpoint is not automatically proof that the selected client can invoke it.

Probe implementations must:

- Be read-only and avoid mutating client/provider configuration.
- Avoid generation calls and other billable model work.
- Use short, bounded timeouts and permit cancellation.
- Preserve diagnostic warnings without dumping credentials.
- Degrade independently: a failed model probe must still permit manual entry.
- Record the effective client/provider/model again during run preflight,
  because authoring-time discovery can become stale.

Provider discovery is implemented once by the provider adapter and reused by
compatible clients. In particular, each harness adapter must not grow its own
provider probing or configuration strategy.

## Run preflight

Authoring and `rb doctor` are read-only. After `rb run` resolves the saved
experiment, but before the first model invocation, the conductor performs a
bounded current-toolchain preflight:

- Codex uses `codex update`; Pi uses `pi update` and then
  `pi update --extensions`.
- LM Studio uses `lms runtime update --all --yes` for installed inference
  runtime extensions. The provider transaction then checks
  `lms server status --json`, starts a stopped server, loads an unloaded
  selected model with `lms load <model> --yes`, and verifies the effective
  state with `lms ps --json`. Its rollback handle unloads only a model it
  introduced and stops only a server it started.
- The preflight records exact executable identities, before/after versions,
  extension/runtime identities, update outcomes, and unsupported freshness
  claims. It never updates during an active model or browser-evaluation phase.
- A provider cannot claim that the LM Studio desktop application was updated
  through `lms`; that app-level limitation is recorded explicitly.

Pi-wiggum is a Pi extension rather than a separate client executable. Its
extension and dependency versions therefore belong to harness provenance, and
its native internal repair iterations count against the same bounded
model-work budget as the rest of the Pi run.

## Experiment file

The schema is versioned and the current parser shape is:

```toml
schema_version = "experiment/v1"
name = "codex-luna"
challenge = "busy-intersection/v1"
client = "codex-cli"
provider = "openai-chatgpt"
model = "gpt-5.6-luna"
track = "cloud-subscription"
repetitions = 3

[client_options]
reasoning_effort = "high"
loop = "controlled"
# Independent repetitions are represented by `repetitions` above.
# Evaluator-controlled Ralph repair passes are represented by max_attempts.
# Optional when discovery requires a non-default executable:
# executable = "/opt/codex/bin/codex"

[budget]
max_wall_seconds = 1200
# max_attempts = 1 initial attempt + permitted Ralph repair passes.
max_attempts = 2

[evaluation]
scenario_pack = "traffic-intersection-p0a"

[output]
inbox = "results/inbox"
```

P0-A has no financial input block. Cloud cost evidence is populated from the
provider/harness when available; the ChatGPT subscription path reports cost as
unavailable. Provider billing capabilities determine which execution tracks
are compatible, and the shared challenge/track profile registry validates the
derived `scenario_pack`. `max_attempts` is always one initial attempt plus the
permitted Ralph repair passes. See [`COST_MODEL.md`](COST_MODEL.md) for the
future OpenRouter reference/billing semantics.

`budget.max_wall_seconds` is the shared model/harness work allowance for one
independent run, including its optional Ralph repair. Deterministic browser
evaluation and bundle finalization have separate bounded infrastructure
timeouts and are measured independently; they do not consume model-work time.

The file contains no API keys, session tokens, or copied client credentials.
It may refer to an environment variable or credential profile by name. Runtime
preflight records requested and effective configuration—with secrets
redacted—in the immutable result bundle.

When the operator supplies a non-default client executable, the wizard writes
that non-secret path to `client_options.executable`; later preflight must use
the recorded path rather than silently returning to `PATH` discovery.

Unknown fields and unsupported client/provider combinations should fail with a
specific validation message. The wizard should use the same schema and
semantic validator as `rb run`; it must not create configurations the conductor
cannot execute.

## Reproducibility boundary

Interactive authoring and experiment execution are separate phases:

```text
environment probes + user choices -> validated experiment.toml
validated experiment.toml + runtime preflight -> immutable run bundle(s)
```

The wizard's convenience state is not authoritative evidence. Each bundle
records the experiment file or its canonical representation, its hash, probe
and preflight differences that affect interpretation, and the effective SUT
identity.

## P0 implementation boundary

P0 includes:

- The `rb` console entry point and `python -m ralph_bench` fallback.
- A testable prompt/navigation engine separated from terminal I/O.
- Client-first zero-argument authoring.
- Fake discovery adapters covering success, partial discovery, timeouts, and
  manual fallback.
- The built-in harness/provider/model registry and capability resolver as the
  only source of wizard choices and option schemas.
- Current-version Codex CLI detection, bounded update-aware preflight,
  read-only ChatGPT authentication through `codex login status`, and the
  `gpt-5.6-luna` model descriptor.
- A provider choice labeled **ChatGPT (subscription)** whose review explains
  that P0-A cost is unavailable, while time, tokens, and attempts remain
  visible. There is no subscription-cost questionnaire.
- Deterministic TOML rendering, validation, atomic saving, and overwrite
  protection.
- A non-interactive run path that never prompts after validation.
- The zero-argument path asks once, after a successful atomic save, before any
  generation can begin. Enter means yes; no leaves the saved experiment
  untouched.
- Concise run progress covers preflight, each model attempt, public checks,
  optional repair, browser evaluation/capture, and bundle finalization. A
  running model attempt emits at most one heartbeat per minute.
- In an interactive terminal, a single `c` key requests a bounded local status
  summary without Enter or another inference call. The summary reports only
  structural evidence: event/tool/error counts, latest-event age, workspace
  file/byte counts, and stderr size. It never prints model prose.
- After bundles are finalized, an interactive run asks whether to open the
  final run's evaluator-recorded WebM overview; Enter means yes. Batch and
  redirected runs never pause. `rb preview <bundle.ralph.zip>` validates the
  bundle and provides the same view later without executing candidate HTML.

P0 does not require universal discovery across every legacy client or a live
online catalog of every provider model. The Pi-wiggum/local execution path is
implemented behind the shared experiment and adapter contracts; its first real
run remains pending selection of a suitable local model. Additional adapters
may improve their discovery capabilities incrementally without changing the
experiment schema.

## Acceptance tests

- With one compatible client installed, `rb` offers it as the visible default.
- With several clients installed, the user can inspect and choose among them.
- With none detected, manual client/executable entry remains possible.
- Provider and model probe failures degrade to labeled manual entry.
- No discovery fixture performs a generation request or writes client config.
- A signed-in Codex fixture resolves ChatGPT subscription plus Luna; a
  signed-out fixture gives `codex login` guidance without reading credentials.
- ChatGPT subscription selection validates without a plan-fee allocation.
- Missing runtime cost evidence remains unavailable/null rather than zero;
  token, time, and attempt evidence remains reportable.
- Back/edit produces the same validated document as entering final answers
  directly.
- Canceling leaves no partial TOML file.
- An existing file is never overwritten without explicit confirmation.
- Generated TOML round-trips through the execution parser and semantic
  validator.
- Secrets present in fixture environments never appear in prompts, TOML,
  diagnostics, or snapshots.
- Zero-argument invocation without a TTY exits clearly and does not hang.
- An explicit `rb run <file>` is deterministic and does not consult wizard
  history.

## Estimate

A skeletal, well-tested wizard with fake probes and deterministic TOML output
is approximately **2–3 engineering days**. Codex detection, authentication
preflight, and ChatGPT/Luna resolution add approximately **1–2 days**. Each
future client is likely **0.5–2 days** for basic detection/configuration and
more when provider/model discovery needs client-specific parsing.
