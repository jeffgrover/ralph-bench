# Ralph Bench

Ralph Bench is a proposed next-generation benchmark for agentic coding systems.
It measures whether a model-and-harness combination can produce an original,
accepted browser artifact, how well that artifact performs, and how much local
time or cloud cost was required to reach it.

The initial challenge family uses visible traffic simulations at two scales:

- **Busy Intersection** for local and smaller models.
- **The 5x5 Rush** for frontier and cloud-class models.

The repository is currently in the planning stage. No implementation contract
is approved until the documents below are reviewed.

## Proposed design documents

- [Vision](docs/VISION.md)
- [P0 implementation plan](docs/P0_PLAN.md)
- [Traffic challenge specifications](docs/TRAFFIC_CHALLENGES.md)
- [Measurement model](docs/MEASUREMENT_MODEL.md)
- [Immutable result bundle](docs/RESULT_BUNDLE.md)
- [Isolation and provenance model](docs/ISOLATION_MODEL.md)
- [Architecture decisions](docs/adr/README.md)

## Intended command shape

```bash
ralph run experiments/local-intersection.toml
ralph build --source results/inbox --output site
```

The run command will create versioned, immutable result bundles. The build
command will validate and aggregate those bundles into a static site without
modifying the source evidence.
