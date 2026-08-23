# Isolation and Provenance Model

**Status:** Accepted
**Date:** 2026-08-23

## Motivation

Prompt instructions are not an isolation boundary. Prior benchmarking showed
that agents may list sibling results, read reference implementations, inspect
hidden evaluator code, or copy artifacts directly. Ralph Bench therefore makes
isolation capability and evidence provenance explicit eligibility data.

## Assets that must be separated

- Ralph Bench source repository.
- Agent-writable submission workspace.
- Prior and concurrent result bundles.
- Reference implementations.
- Private scenarios and judge packs.
- Conductor logs and authoritative timings.
- Finalized bundle staging.
- User credentials and unrelated home-directory data.

The agent receives only public challenge inputs, its writable submission path,
and the minimum configuration required to contact the selected provider.

## Threat model

P0 addresses accidental or opportunistic access by a tool-using agent,
including:

- Traversing parent/sibling directories.
- Reading prior submissions or known-good references.
- Reading hidden tests or thresholds.
- Editing evaluator output or authoritative metrics.
- Reading unrelated user files through inherited home/config paths.
- Leaking credentials into artifacts or logs.
- Fetching published solutions over the network.
- Claiming false telemetry or dropping evaluator-requested work.

P0 does not claim containment against a deliberately malicious native binary,
kernel exploit, provider-side compromise, or every covert channel.

## Isolation levels

### L0 — Unsealed

- A fresh staged workspace may reduce accidental cross-run contamination, but
  confidentiality from other host paths is not independently enforced.
- Provider credentials remain available to the harness parent and may be
  reachable under the harness's native sandbox semantics.
- Suitable for development, local comparison, and explicitly unsealed result
  sharing.
- Not eligible for an official leaderboard.

### L1 — Staged

- Fresh workspace outside source, results, reference, and judge-pack paths.
- Only public challenge inputs are materialized.
- Ephemeral or scoped agent configuration where supported.
- Environment allowlist/redaction.
- Authoritative logs and timers retained by the conductor outside the writable
  submission tree.
- Filesystem/network enforcement may still rely on platform and harness
  behavior.

L1 is deferred until platform backends can be evaluated deliberately. P0 uses
L0 and must not silently upgrade a result based only on staging or a harness's
native sandbox label.

### L2 — Enforced

- OS/container sandbox enforces a filesystem allowlist.
- Process, home/config, and writable paths are constrained.
- Agent shell network is restricted independently from provider communication
  where the platform permits.
- Hidden material and unrelated user data are not reachable.
- Capability is validated with escape/canary tests.

L2 is the proposed minimum for an official public leaderboard.

### L3 — Hardened/reproducible

- Reproducible execution image or declared host profile.
- Strong secret brokerage and provider proxying.
- Network egress policy and audit.
- Signed challenge/judge packs and bundles.
- Stronger syscall/process/resource controls.

L3 is a future deployment target, not a P0 commitment.

## P0 staged workspace

The conductor should create a fresh run root resembling:

```text
<ephemeral-run-root>/
├── public-challenge/   # read-only where supported
├── workspace/          # agent cwd and writable submission
├── public-tools/       # public checker/evaluator client
├── scoped-home/        # minimum runner/provider config
└── conductor/          # not exposed as agent cwd; permissions separated when possible
```

Private evaluation occurs after the agent process stops and uses a separate
workspace containing the selected candidate plus the judge pack.

The source repo, legacy benchmark, prior bundles, reference solutions, and
private judge pack are never copied into the run root.

## Configuration handling

Configuration follows the centralized lifecycle defined in
[`CONFIGURATION_MODEL.md`](CONFIGURATION_MODEL.md):

- The validated experiment is the single source of requested intent.
- The conductor resolves and orders configuration actions.
- A provider adapter exclusively owns provider/runtime setup and observation;
  a harness adapter exclusively owns its scoped native client configuration.
- Prefer explicit per-run config paths and environment overlays inside an
  ephemeral HOME/XDG/config directory.
- Do not silently inherit user-global client configuration. Copy or broker only
  explicitly referenced authentication material, with minimal permissions.
- Never archive the scoped home, native credential material, or unredacted
  configuration as an artifact.
- Record requested, materialized, effective, and cleanup configuration as
  distinct redacted evidence.
- Snapshot authorized external state, register rollback before mutation, and
  verify restoration after success, failure, cancellation, and timeout.

Client/provider idempotence includes preflight state, a reviewable action plan,
effective configuration, cleanup, and post-run verification. In particular,
a future LM Studio lifecycle would be implemented once by its provider adapter,
not separately by every harness adapter.

### P0 Codex and ChatGPT authentication

The P0 live SUT reuses operator-managed ChatGPT authentication for Codex CLI.
`rb` may execute `codex login status` and use the existing supported credential
mechanism, but it must not copy an auth cache into the challenge workspace,
print tokens, or archive credential files.

The benchmarked agent's tool shell must not be able to read ChatGPT tokens or
the Codex authentication cache. Prefer an OS credential store or an enforced
credential boundary that remains available to the Codex process but outside
agent tool access. `--ephemeral` prevents session persistence; it is not by
itself a credential-isolation guarantee.

P0-A reuses the operator's existing Codex authentication, runs in a fresh
workspace, filters the inherited environment, requests Codex's native
`workspace-write` sandbox, keeps conductor-owned output outside the submission
tree, and redacts known credential values from captured vendor streams. It
does not run a credential canary or claim that unrelated host files, judge
material, or credentials are unreadable to a determined agent. Every such run
is recorded as L0/unsealed.

Selection among Bubblewrap, Seatbelt/App Sandbox, WSL/Windows facilities,
containers, and virtual machines is a later cross-platform design milestone.
The conductor's provenance contract—not any one tool—is the durable boundary.

## Network policy

Cloud and local-provider harnesses need model communication, but their shell
tools do not necessarily need unrestricted network access. Strongly separating
those channels is platform-dependent.

P0 therefore:

- Records whether agent-tool network access was unrestricted, restricted, or
  unknown.
- Avoids placing private material in public remote repositories.
- Uses hidden scenario variation so a fetched public artifact is insufficient.
- Treats transcript/path audits as defense in depth, not proof of isolation.

Provider proxying and per-process egress controls are candidates for L2/L3.

## Conductor-owned evidence

The agent cannot author or overwrite:

- Run identity and experiment identity.
- Monotonic phase timings.
- Raw process stdout/stderr capture.
- Private scenarios and assertion results.
- Bundle inventory and checksums.
- Isolation capability report.
- Final validity decision.

The candidate may emit public telemetry through `traffic/v1`, but authoritative
metrics reconcile it against evaluator-issued trip IDs, independent snapshots,
network geometry, and browser observations.

## Provenance capture

Record at least:

- Source and challenge versions.
- Public and private pack digests.
- Harness binary/version and command shape with secrets redacted.
- Model/provider identifiers and requested/effective settings.
- Cloud billing mode, cost/reference status, and redacted billing, model
  mapping, pricing-snapshot, and evidence provenance.
- Tool policy and network capability.
- Hardware, OS, browser, Node, Python, inference runtime, and relevant driver
  versions.
- Workspace/isolation implementation and capability flags.
- Start/end and monotonic phase durations.
- Agent configuration restoration result.
- Candidate and bundle hashes.

For local inference, include context, quantization, load options, concurrency,
and effective server/model configuration where observable.

## Taint and invalidation

Structured taint reasons include:

- Verified read/copy of a reference solution.
- Verified access to another run's artifact.
- Verified access to a private judge pack.
- Candidate or evidence modified after the agent/evaluation boundary.
- Missing or failed checksum/provenance checks.
- Unexplained trip/telemetry inconsistency beyond tolerance.

Tainted bundles remain inspectable but are excluded from official ranking.
Deletion is not the default response; preserving evidence helps improve the
isolation system.

## Canary and audit tests

P0 should include tests that:

- Place a canary filename outside the staged workspace and confirm public tools
  do not reveal it.
- Attempt parent traversal from fixture agents.
- Attempt to alter conductor-owned files.
- Verify private evaluation starts only after the agent stops.
- Scan normalized tool events for paths outside allowed roots.
- Detect secrets intentionally placed in fixture configuration.
- Confirm a Codex fixture agent cannot read the selected ChatGPT credential
  store/cache or receive tokens through its tool environment.

Successful audits increase confidence but do not upgrade L1 to L2 without
enforced controls.

## Publication policy

The reporter displays isolation and metric-quality badges prominently.

- L0 results appear only in development/legacy views.
- L1 results may appear in an experimental view.
- Official ranking is proposed to require L2 plus complete evidence.
- Any exception must be an explicit, versioned publication policy rather than
  an undocumented manual decision.
