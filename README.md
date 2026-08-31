# Ralph Bench

Ralph Bench is a next-generation benchmark for agentic coding systems.
It measures whether a model-and-harness combination can produce an original,
accepted browser artifact, how well that artifact performs, and how much local
time or cloud cost was required to reach it.

The initial challenge family uses visible traffic simulations at two scales:

- **Busy Intersection** for local and smaller models.
- **The 5x5 Rush** for frontier and cloud-class models.

Busy Intersection is the primary current challenge. The 5x5 Rush is a future
city extension; the P0 seam proof is named the **Challenge Portability
Fixture**. It exists to prove that future challenges can enter through the
generic challenge boundary without requiring Busy Intersection-specific
conductor logic. It does not prescribe the future city's topology or protocol.

The initial live system under test is:

```text
Codex CLI x ChatGPT-managed OpenAI access x gpt-5.6-luna
```

It is a cloud-subscription path whose P0-A cost is explicitly unavailable;
time, token, and attempt evidence remain reportable. Codex is refreshed to the
most recent available release before a run and its exact version is recorded.
The Pi-wiggum execution and evidence path is also prepared behind the same
conductor seam. For controlled proving runs, Pi loads the installed Wiggum
extension guards while Ralph owns the bounded repair loop and browser feedback;
the Wiggum TPM prompt is reserved for `loop = "native"`. OpenRouter remains
the next provider slice for billed and normalized reference pricing.

P0-A targets a seam-complete Busy Intersection vertical slice. The Challenge
Portability Fixture remains a small second-challenge boundary proof; it is not
a partial city simulation and does not constrain the future city's topology or
protocol. Static reporting is now implemented as the first derived product
surface; full future-city work follows the remaining acceptance and portability
seams.

The P0-A planning packet was accepted on 2026-08-23, as amended by [ADR
0011](docs/adr/0011-cloud-cost-evidence-and-openrouter-references.md),
[ADR 0014](docs/adr/0014-seam-first-evaluation-and-active-harness.md), and
[ADR 0015](docs/adr/0015-current-toolchain-preflight.md); implementation is
underway. P0-A does not allocate subscription fees;
OpenRouter billing/reference support is the next provider slice.

## P0-A design documents

- [Vision](docs/VISION.md)
- [P0 implementation plan](docs/P0_PLAN.md)
- [Prioritized next steps](docs/NEXT_STEPS.md)
- [`rb` CLI and experiment authoring](docs/CLI_AND_EXPERIMENTS.md)
- [Configuration ownership and lifecycle](docs/CONFIGURATION_MODEL.md)
- [Polymorphic harness, provider, and model adapters](docs/ADAPTER_MODEL.md)
- [Traffic challenge specifications](docs/TRAFFIC_CHALLENGES.md)
- [Measurement model](docs/MEASUREMENT_MODEL.md)
- [Cloud and subscription cost model](docs/COST_MODEL.md)
- [Immutable result bundle](docs/RESULT_BUNDLE.md)
- [Isolation and provenance model](docs/ISOLATION_MODEL.md)
- [Architecture decisions](docs/adr/README.md)

## Intended command shape

```bash
rb
rb run experiments/cloud-intersection.toml
rb conformance tests/fixtures/busy_intersection/passing
rb preview results/inbox/<run-id>.ralph.zip
rb build --source results/inbox --output site
```

With no arguments, `rb` guides the user through a client-first experiment
wizard, safely probes the selected client for compatible providers and models,
writes a validated TOML specification, and asks whether to run it immediately.
The confirmation states the number of independent runs and maximum model
invocations before accepting Enter as yes. Explicit commands
remain deterministic and automation-friendly.

After an interactive evaluation, `rb` offers to open the final run's recorded
simulation overview, defaulting to yes. It opens evaluator-owned WebM evidence
rather than executing candidate HTML. `rb preview` provides the same operation
later for any validated result bundle. Noninteractive runs never prompt.

The run command creates versioned, immutable result bundles for evaluated
candidates. Complete pre-evaluation failures with no candidate or no started
evaluator fail fast without creating a diagnostic bundle. The build command
will validate and aggregate result bundles into a static site without
modifying the source evidence.

## Current implementation slice

The first P0-A contract spine is implemented and tested:

- `rb`/`rb configure` provides client-first experiment authoring with read-only
  Codex and ChatGPT probes; P0-A has no subscription-cost questionnaire.
- `rb doctor` reports bounded Codex detection plus Chromium and Playwright
  video readiness without exposing command output.
- `rb bundle validate` performs read-only validation of the P0-A immutable
  bundle profile.
- Cost evidence uses the generic `actual_cost_usd` and
  `reference_cost_usd` fields with required matching source fields. Status is
  independent, and P0-A records flat-subscription cost as unavailable with an
  explicit reason; OpenRouter is the canonical reference authority for the
  next provider slice and appears in source/UI provenance rather than a field
  name.
- Provider billing capabilities select compatible tracks, while the shared
  challenge/track scenario-profile registry derives and validates the
  persisted scenario pack in both the wizard and experiment parser.
- The conductor attempt loop, staged-workspace protection, canonical events,
  unavailable-subscription cost evidence, and deterministic bundle finalizer
  are connected as one live path.
- Each Codex run uses a fresh staged workspace, a sanitized child environment,
  and Codex's native `workspace-write` sandbox. P0 records this honestly as
  L0/unsealed: credential confidentiality and read isolation from unrelated
  host files are not proven.
- Busy Intersection ships a public `gates/v1` pack: Ralph injects two arrival
  callbacks and two finish notifications, owns completion timestamps and the
  issued/completed/outstanding ledger, and samples that ledger while a killable
  offline Playwright worker records the same live run as a validated poster and
  WebM overview. The scored load schedule is not staged with the candidate.
- `rb run` reports concise phase transitions and a once-per-minute heartbeat
  while a model attempt is still running; vendor-native output is redacted and
  preserved as bundle evidence rather than flooding the console. In an
  interactive terminal, pressing `c` during a model attempt prints a local,
  content-free progress check (event/tool/error counts, latest event age,
  workspace size, and stderr size) without invoking another model.
- Pi refreshes itself and its installed extension graph before a run, writes
  scoped LM Studio provider configuration, and normalizes Pi JSONL evidence.
  Controlled Pi attempts stop when a new `index.html` candidate is written;
  browser/runtime failures become bounded semantic feedback for the one repair
  attempt, without exposing private load values.
- Functional eligibility includes the held-load and cooldown outcomes while
  retaining a separate performance-eligibility flag. A working but overloaded
  artifact remains measurable but cannot be reported as a full pass.
- `rb conformance <candidate>` runs the checked-in, unscored public
  `gates/v1` smoke schedule and reports registration, delivery, completion,
  runtime, and offline diagnostics without exposing private scoring demand.
- Challenge-specific public-pack preparation, scenario construction, browser
  evaluation, repair vocabulary, and prompts traverse a challenge adapter
  boundary rather than a Busy Intersection branch in the conductor.
- `rb build --source <inbox> --output <site>` validates bundles read-only and
  produces a deterministic static report with local/cloud track context,
  acceptance/failure evidence, resource metrics, provenance, poster/video
  captures, and explicit artifact download links. Candidate HTML is never
  executed by the report shell; invalid bundles are quarantined from normal
  views.

The remaining P0-A seams are the portability fixture's full generic lifecycle
proof, reproducibility/claim hardening, and cross-platform validation.
Current-toolchain refresh and local-provider readiness are required run-preflight
seams before model evaluation; discovery and `rb doctor` remain read-only.

The first local proving candidate was attempted with
`gemma-4-12b-it-mlx`. It reached static and browser evaluation in one run but
did not complete a passing repair within the bounded local model budget; no
passing bundle was manufactured. That result is useful calibration: the local
path and evaluator feedback seam are live, while this model still needs either
a better tool-call strategy or a stronger model to clear the working-solution
bar. A second local trial with `gpt-oss-20b` reached browser evaluation on both
attempts but serviced no evaluator demand; its corrected diagnostic bundle is
preserved in the local results inbox. A successful real-model bundle is not
required for fixture-driven seam work, but is still needed to calibrate
real-model capacity comparisons.

### Platform posture

P0 deliberately has no required OS-specific isolation tool. The protection
contract is portable best effort; strong L1/L2 backends are deferred until
their behavior can be designed and compared across Linux, macOS, and Windows.
The current end-to-end implementation is developed and tested on Linux.
Windows and macOS still require broader process-lifecycle validation before
they can be called supported, but the macOS evaluator now prefers Playwright's
standalone headless shell. This avoids launching the user's interactive Chrome
app, which can abort during headless startup. Bubblewrap is no longer a
prerequisite or an architectural commitment.

For development:

```bash
uv venv
uv sync
source .venv/bin/activate
rb --help
.venv/bin/python -m unittest discover -s tests -v
```
