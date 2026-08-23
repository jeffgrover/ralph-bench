# Ralph Bench

## Project overview

Ralph Bench is a greenfield benchmark for agentic coding systems. It evaluates
whether a model-and-harness combination can produce an original, accepted
browser artifact, how well the artifact performs under controlled load, and
how much local time or cloud cost was required.

The P0 challenge family is:

- `busy-intersection/v1` for local and smaller models.
- `five-by-five-rush/v1` for frontier and cloud-class models.

Both challenges use the proposed `traffic/v1` evaluator protocol and optimize
for sustainable valid vehicle throughput under fixed safety, fairness,
physical, infrastructure, spillback, and recovery constraints.

## Repository identity

- The canonical GitHub repository owner is the personal account `jeffgrover`.
- Do not commit or push this project using the work account `jeff-grover` or a
  work email address.
- Before committing or pushing, verify that the repository-local author identity
  and active GitHub authentication both resolve to the personal account. Stop
  and ask the user if either identity is uncertain.
- Do not rewrite existing published history to change attribution without the
  user's explicit approval.

## Authoritative planning documents

Read these before P0 implementation:

- `docs/VISION.md`
- `docs/P0_PLAN.md`
- `docs/CLI_AND_EXPERIMENTS.md`
- `docs/CONFIGURATION_MODEL.md`
- `docs/ADAPTER_MODEL.md`
- `docs/TRAFFIC_CHALLENGES.md`
- `docs/MEASUREMENT_MODEL.md`
- `docs/RESULT_BUNDLE.md`
- `docs/ISOLATION_MODEL.md`
- `docs/adr/`

The documents and ADRs are marked `Proposed` until the user approves them. Do
not silently resolve an unapproved product decision through implementation.

## Architectural constraints

- This is a greenfield repository. Consult the legacy `llm-eval` repository
  selectively, but do not reproduce its directory-name identity, report-time
  mutation, or run/report coupling.
- The installed command is `rb`. With no arguments in an interactive terminal,
  it starts a client-first experiment wizard; explicit commands remain
  available for deterministic automation.
- Use `client` in the user-facing experiment format and interface. Internally,
  client execution is implemented by a `HarnessAdapter`.
- Treat harnesses, providers, and models as separate typed polymorphic adapter
  families composed into a `ResolvedSUT` through capability negotiation. Do not
  add cross-product runners or scatter vendor-name branches through the
  conductor, wizard, or reporter.
- Most model adapters should be declarative descriptors; unknown models use a
  conservative generic adapter. Do not require a code class per model ID or
  invent capabilities for an unrecognized model.
- P0 uses an explicit built-in adapter registry and shared conformance suites.
  Arbitrary third-party adapter loading is post-P0.
- Discovery must be read-only, non-billable, bounded, provenance-labeled, and
  able to degrade to manual provider/model entry. It must never copy secrets
  into an experiment file.
- The wizard and `rb run` must share the same schema and semantic validation.
  Saved TOML is authoritative for execution; remembered wizard state is not.
- The conductor centrally owns configuration resolution and lifecycle. Provider
  adapters own provider setup/observation; harness adapters own scoped native
  client configuration. Do not configure a provider independently inside each
  harness adapter or silently inherit user-global configuration.
- Preserve requested, materialized, effective, and cleanup configuration as
  distinct redacted evidence. Setup must register rollback, and cleanup must be
  attempted after success, failure, cancellation, and timeout.
- Every repetition receives a unique run ID and produces one immutable,
  checksummed `.ralph.zip` bundle.
- Run identity and metadata come from manifests, never filenames or HTML.
- The run path does not generate `summary.html` or any other authoritative
  report.
- Reporting is a read-only transform over validated bundles and writes to a
  separate site directory.
- Agent workspaces must not contain prior results, reference implementations,
  private judge packs, source-repository internals, or conductor-owned evidence.
- Public challenge packs and private judge packs are separate inputs.
- The evaluator supplies and accounts for traffic demand; the artifact cannot
  choose how much work it receives.
- The Busy Intersection may use 2D, 2.5D, or 3D presentation. Do not encode a
  rendering-technology preference into traffic acceptance or visual review.
- Treat layout, visual coherence, information design, motion, polish,
  originality, and delight as explicit human-review dimensions, while keeping
  them separate from traffic validity and throughput.
- Authoritative timings, private checks, validity, bundle inventory, and
  checksums are conductor-owned.
- Keep native harness loops and evaluator-controlled repair loops explicitly
  labeled and separate.
- Missing, estimated, provider-reported, and evaluator-measured values are not
  interchangeable; metric provenance is required.
- Do not introduce a single composite overall score during P0.

## P0 implementation posture

- Implement the Busy Intersection vertical slice before city-specific logic.
- Begin with deterministic fixture artifacts and harness adapters before
  invoking a real model.
- The only required live P0 SUT is Codex CLI with ChatGPT-managed OpenAI access
  and `gpt-5.6-luna`, classified as `cloud-subscription`. Reasoning effort is an
  explicit experiment setting.
- Use `codex exec` non-interactively with JSONL evidence, an explicit model and
  sandbox, ephemeral session state, and isolated or ignored user configuration.
  Pin and record the tested Codex CLI version.
- Authentication is operator-managed. Probe it read-only with
  `codex login status`; never copy, print, archive, or silently replace ChatGPT
  credentials.
- Treat ChatGPT-backed cost as subscription/unmetered and USD as unavailable,
  never zero or estimated from API list pricing.
- OpenCode, LM Studio, API-key-metered OpenAI, local models, and all other live
  harness/provider/model integrations are TBD and post-P0 unless the plan is
  amended.
- P0 targets staged L1 isolation and must label its limitations honestly.
- Exact traffic thresholds belong in versioned private judge packs and require
  fixture/reference/pilot calibration.
- Google Drive, legacy result import, frontier-model qualitative judging, and
  broad legacy-harness migration are post-P0 work.

## Engineering guidance

- Prefer small modules with typed domain objects and pure calculation functions.
- Keep vendor parsing at adapter boundaries and preserve raw vendor evidence.
- Use monotonic clocks for durations and wall timestamps only for correlation.
- Make IDs, clocks, filesystem roots, and process execution injectable in tests.
- Treat bundle creation and extraction as security-sensitive code.
- Validate paths, sizes, schemas, checksums, and internal references before
  ingest.
- Never archive credentials or an agent's scoped home directory.
- Preserve partial and failed evidence; do not overwrite it with later attempts.
- Keep challenge-specific checks out of the conductor core.
- Ensure deterministic fast-forward evaluation and visible playback use the
  same simulation state/update path.

## Testing expectations

P0 tests must cover:

- Client detection, partial/failed discovery, intelligent defaults, wizard
  navigation, TOML round-tripping, cancellation, and non-interactive behavior.
- Codex CLI version/auth preflight fixtures, JSONL normalization, explicit Luna
  selection, ChatGPT credential-canary isolation, and subscription/unmetered
  cost provenance.
- Schema/version handling and run state transitions.
- Unique IDs and non-overwriting repetitions.
- Attempt preservation and controlled feedback.
- Isolation/path and secret-redaction fixtures.
- Malformed and adversarial ZIP bundles.
- Passing and deliberately broken traffic artifacts.
- Dishonest or inconsistent artifact telemetry.
- Load-to-failure, recovery, and metric calculations.
- Bundle-to-static-site end-to-end behavior.

Unit and fixture integration tests must run without a model account, inference
server, or private judge material.
