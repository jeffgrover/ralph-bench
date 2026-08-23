# ADR 0003: Sustainable Valid Throughput

**Status:** Proposed
**Date:** 2026-08-23

## Context

Binary runtime checks do not distinguish increasingly capable artifacts. Raw
vehicle throughput is differentiating but can be gamed through unsafe behavior,
ignored demand, unrealistic physics, starvation, or unbounded infrastructure.

The initial challenge family needs a measurable optimization target that also
matches what a human recognizes as good traffic design.

## Decision

Use **sustainable valid throughput** as the primary traffic optimization
metric. The evaluator controls trip demand and raises it through held stages
until the artifact reaches a versioned safety, accounting, fairness,
queue-containment, recovery, or runtime failure condition.

Report both:

- Breakdown capacity: highest qualifying offered demand.
- Peak sustainable throughput: highest qualifying valid completion rate.

Also report ordinary-load delay/fairness and post-overload recovery. Fix the
physical and infrastructure envelope per challenge version.

## Consequences

### Positive

- Passing artifacts continue to differentiate.
- Optimization rewards system design rather than source-pattern compliance.
- Capacity, normal behavior, and resilience are visible separately.
- The load-to-failure curve creates compelling standardized captures.

### Negative

- Thresholds and stage durations need empirical calibration.
- Evaluation is more expensive than a single smoke test.
- Telemetry needs independent reconciliation.
- Traffic profiles yield a vector of capacities rather than one naturally
  universal value.

## Rejected alternatives

- Count vehicles passing one detector without complete trip accounting.
- Score only a fixed low-demand scenario.
- Require literal zero queueing during rush hour.
- Combine unsafe throughput and safety penalties into one tradeable number.
