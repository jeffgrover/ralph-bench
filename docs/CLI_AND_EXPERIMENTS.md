# `rb` CLI and Experiment Authoring

**Status:** Proposed
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
rb configure experiments/local-intersection.toml
rb run experiments/local-intersection.toml
rb bundle validate results/inbox/<run-id>.ralph.zip
rb build --source results/inbox --output site
```

`rb run` with no experiment path may enter the same wizard. In a non-interactive
environment, commands that need answers fail with an actionable message rather
than guessing.

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

The first substantive question is always the client. A proposed P0 flow is:

1. **Client** — show detected compatible clients, executable paths, versions,
   and detection status.
2. **Provider** — show providers supported or configured for that client,
   separated into local and cloud choices.
3. **Model** — query the selected client/provider where possible and show model
   IDs with the source and freshness of the discovery.
4. **Challenge** — default according to the selected local/cloud track while
   allowing either challenge when compatible.
5. **Client and model controls** — reasoning/effort, tool policy, native versus
   controlled loop, and adapter-specific supported options.
6. **Evaluation controls** — repetitions, wall-time or cost budget, repair
   attempts, scenario-pack reference, and isolation choice.
7. **Destination** — propose a readable, collision-free filename under
   `experiments/`.
8. **Review** — render the complete TOML, provenance of inferred defaults, and
   warnings; allow the user to move back and edit any section.
9. **Validate and save** — write atomically, never silently overwrite, and
   report the exact path.
10. **Run** — offer to execute the saved experiment. Cloud runs show the
    requested cost controls and require explicit confirmation.

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
3. A currently active or uniquely detected client/provider/model.
4. A challenge- or adapter-defined safe default.
5. No default; require a choice.

Remembered UI state may accelerate authoring but must never affect execution of
an already saved experiment. Environment-derived values are resolved into the
TOML or recorded as explicit runtime references. The final review identifies
which values were selected, inferred, or entered manually.

Defaults must be cost-aware. Discovery does not send a generation request.
Selecting a cloud provider does not authorize a run, and an unknown cloud cost
must not be presented as zero.

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

## Experiment file

The schema remains versioned and the exact fields remain provisional until the
first adapters exercise them. The intended shape is:

```toml
schema_version = "experiment/v1"
name = "codex-chatgpt-luna-intersection"
challenge = "busy-intersection/v1"
client = "codex-cli"
provider = "openai-chatgpt"
model = "gpt-5.6-luna"
track = "cloud-subscription"
repetitions = 3

[client_options]
reasoning_effort = "high"
loop = "controlled"

[budget]
max_wall_seconds = 1200
max_attempts = 2

[evaluation]
scenario_pack = "traffic-local-p0"

[output]
inbox = "results/inbox"
```

The file contains no API keys, session tokens, or copied client credentials.
It may refer to an environment variable or credential profile by name. Runtime
preflight records requested and effective configuration—with secrets
redacted—in the immutable result bundle.

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
- Real Codex CLI detection, read-only ChatGPT authentication preflight through
  `codex login status`, and the `gpt-5.6-luna` model descriptor.
- A provider choice labeled **ChatGPT (subscription)** with unmetered cost
  provenance and no implied per-run USD value.
- Deterministic TOML rendering, validation, atomic saving, and overwrite
  protection.
- A non-interactive run path that never prompts after validation.

P0 does not require universal discovery across every legacy client or a live
online catalog of every provider model. Additional adapters may improve their
discovery capabilities incrementally without changing the experiment schema.

## Acceptance tests

- With one compatible client installed, `rb` offers it as the visible default.
- With several clients installed, the user can inspect and choose among them.
- With none detected, manual client/executable entry remains possible.
- Provider and model probe failures degrade to labeled manual entry.
- No discovery fixture performs a generation request or writes client config.
- A signed-in Codex fixture resolves ChatGPT subscription plus Luna; a
  signed-out fixture gives `codex login` guidance without reading credentials.
- ChatGPT subscription selection renders USD cost as unavailable, never zero.
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
