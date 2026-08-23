# Ralph Bench

Ralph Bench is a next-generation benchmark for agentic coding systems.
It measures whether a model-and-harness combination can produce an original,
accepted browser artifact, how well that artifact performs, and how much local
time or cloud cost was required to reach it.

The initial challenge family uses visible traffic simulations at two scales:

- **Busy Intersection** for local and smaller models.
- **The 5x5 Rush** for frontier and cloud-class models.

The P0 live system under test is:

```text
Codex CLI x ChatGPT-managed OpenAI access x gpt-5.6-luna
```

It is a cloud-subscription path whose P0-A cost is explicitly unavailable;
time, token, and attempt evidence remain reportable. OpenRouter is the next
provider slice for billed and normalized reference pricing. Other real
harnesses, providers, and models remain TBD; deterministic fake adapters
preserve polymorphic contract coverage during P0.

P0-A completes one Busy Intersection vertical slice through every durable
boundary. The 5x5 Rush is retained as a contract/fixture in P0-A and becomes
the P0-B challenge-generalization milestone.

The P0-A planning packet was accepted on 2026-08-23, as amended by [ADR
0011](docs/adr/0011-cloud-cost-evidence-and-openrouter-references.md), and
implementation is underway. P0-A does not allocate subscription fees;
OpenRouter billing/reference support is the next provider slice.

## P0-A design documents

- [Vision](docs/VISION.md)
- [P0 implementation plan](docs/P0_PLAN.md)
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

The run command creates versioned, immutable result bundles. The build
command will validate and aggregate those bundles into a static site without
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
- The conductor attempt loop, staged-workspace isolation, canonical events,
  unavailable-subscription cost evidence, and deterministic bundle finalizer
  are connected as one live path.
- Each Codex run uses a fresh staged workspace, a sanitized child environment,
  and Codex's native `workspace-write` sandbox. P0 records this honestly as
  L0/unsealed: credential confidentiality and read isolation from unrelated
  host files are not proven.
- Busy Intersection ships a public `traffic/v1` pack, deterministic load
  schedule with rotating seeds, evaluator-owned physical constraints,
  anti-fabrication lifecycle/fairness checks, and a killable offline Playwright
  worker that produces a validated poster and WebM overview from the evaluated
  artifact.
- `rb run` reports concise phase transitions and a once-per-minute heartbeat
  while a model attempt is still running; vendor-native output is redacted and
  preserved as bundle evidence rather than flooding the console. In an
  interactive terminal, pressing `c` during a model attempt prints a local,
  content-free progress check (event/tool/error counts, latest event age,
  workspace size, and stderr size) without invoking another model.

`rb build` remains the unimplemented P0-A boundary. Static reporting is the
next implementation wave.

### Platform posture

P0 deliberately has no required OS-specific isolation tool. The protection
contract is portable best effort; strong L1/L2 backends are deferred until
their behavior can be designed and compared across Linux, macOS, and Windows.
The current end-to-end implementation is developed and tested on Linux.
Windows and macOS still require browser discovery and process-lifecycle
validation before they can be called supported, but Bubblewrap is no longer a
prerequisite or an architectural commitment.

For development:

```bash
uv venv
uv sync
source .venv/bin/activate
rb --help
.venv/bin/python -m unittest discover -s tests -v
```
