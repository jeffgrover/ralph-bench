# ADR 0004: Controlled and Native Loops

**Status:** Proposed
**Date:** 2026-08-23

## Context

Agent harnesses differ substantially in planning, tool use, self-verification,
and repair behavior. An evaluator-owned Ralph-style loop can equalize feedback
and expose repairability, but it also changes the product being benchmarked.
Combining native and evaluator-controlled results would obscure what caused the
outcome.

## Decision

Maintain two explicitly labeled benchmark tracks:

- **Native track:** the harness owns its internal iteration and debugging
  within a fixed overall budget.
- **Controlled track:** the evaluator ends an attempt, runs public checks, and
  may provide versioned structured feedback for another attempt.

P0 implements the controlled lifecycle with at most one repair attempt and
records first-attempt and final outcomes separately. The architecture must not
prevent a later native track.

Private hidden-test details are not fed back during the run.

## Consequences

### Positive

- First-pass quality and repairability remain visible.
- Harness-native product performance is not mislabeled as controlled-loop
  performance.
- Feedback format and maximum attempts can be versioned.
- Failed attempts remain useful evidence.

### Negative

- Two tracks create more result dimensions and UI complexity.
- Controlled attempts add time and cost.
- Public-check design must avoid leaking private holdouts.

## Rejected alternatives

- Treat every harness turn as an evaluator repair attempt.
- Feed hidden judge output directly back to the agent.
- Combine native and controlled results in one leaderboard without labels.
