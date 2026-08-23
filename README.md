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

It is a cloud-subscription path with mandatory, explicitly allocated cost.
Other real harnesses, providers, and models remain TBD; deterministic fake
adapters preserve polymorphic contract coverage during P0.

P0-A completes one Busy Intersection vertical slice through every durable
boundary. The 5x5 Rush is retained as a contract/fixture in P0-A and becomes
the P0-B challenge-generalization milestone.

The P0-A planning packet was accepted on 2026-08-23 and implementation is now
underway. The documents below are the approved product and architecture
contracts for this milestone.

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
rb build --source results/inbox --output site
```

With no arguments, `rb` will guide the user through a client-first experiment
wizard, safely probe the selected client for compatible providers and models,
write a validated TOML specification, and offer to run it. Explicit commands
remain deterministic and automation-friendly.

The run command will create versioned, immutable result bundles. The build
command will validate and aggregate those bundles into a static site without
modifying the source evidence.

## Current implementation slice

The first P0-A contract spine is implemented and tested:

- `rb`/`rb configure` provides client-first experiment authoring with read-only
  Codex and ChatGPT probes and explicit subscription-cost inputs.
- `rb doctor` reports bounded Codex detection without exposing command output.
- `rb bundle validate` performs read-only validation of the P0-A immutable
  bundle profile.
- The conductor attempt loop, staged-workspace isolation, canonical events,
  subscription pool accounting, and deterministic bundle finalizer are usable
  as Python contracts.

`rb run` and `rb build` are registered but deliberately fail closed in this
slice; live model execution, traffic evaluation/capture, and static reporting
are the next implementation waves.

For development:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m unittest discover -s tests -v
```
