# Ralph Bench

Ralph Bench is a proposed next-generation benchmark for agentic coding systems.
It measures whether a model-and-harness combination can produce an original,
accepted browser artifact, how well that artifact performs, and how much local
time or cloud cost was required to reach it.

The initial challenge family uses visible traffic simulations at two scales:

- **Busy Intersection** for local and smaller models.
- **The 5x5 Rush** for frontier and cloud-class models.

The proposed P0 live system under test is:

```text
Codex CLI x ChatGPT-managed OpenAI access x gpt-5.6-luna
```

It is a cloud-subscription/unmetered path. Other real harnesses, providers, and
models remain TBD; deterministic fake adapters preserve polymorphic contract
coverage during P0.

The repository is currently in the planning stage. No implementation contract
is approved until the documents below are reviewed.

## Proposed design documents

- [Vision](docs/VISION.md)
- [P0 implementation plan](docs/P0_PLAN.md)
- [`rb` CLI and experiment authoring](docs/CLI_AND_EXPERIMENTS.md)
- [Configuration ownership and lifecycle](docs/CONFIGURATION_MODEL.md)
- [Polymorphic harness, provider, and model adapters](docs/ADAPTER_MODEL.md)
- [Traffic challenge specifications](docs/TRAFFIC_CHALLENGES.md)
- [Measurement model](docs/MEASUREMENT_MODEL.md)
- [Immutable result bundle](docs/RESULT_BUNDLE.md)
- [Isolation and provenance model](docs/ISOLATION_MODEL.md)
- [Architecture decisions](docs/adr/README.md)

## Intended command shape

```bash
rb
rb run experiments/local-intersection.toml
rb build --source results/inbox --output site
```

With no arguments, `rb` will guide the user through a client-first experiment
wizard, safely probe the selected client for compatible providers and models,
write a validated TOML specification, and offer to run it. Explicit commands
remain deterministic and automation-friendly.

The run command will create versioned, immutable result bundles. The build
command will validate and aggregate those bundles into a static site without
modifying the source evidence.
