# ADR 0003: Sustainable Throughput with Validity Gates

**Status:** Accepted
**Date:** 2026-08-23

Candidate-facing measurement details are amended by
[ADR 0013](0013-minimal-gates-interface.md): P0 uses evaluator-owned gate
ledgers plus recorded visual review rather than a topology/snapshot/event
contract.

## Context

Binary runtime checks do not distinguish increasingly capable artifacts. Raw
vehicle throughput is differentiating but can be gamed through unsafe behavior,
ignored demand, unrealistic physics, starvation, or unbounded infrastructure.

The initial challenge family needs a measurable optimization target that also
matches what a human recognizes as good traffic design.

## Decision

Use sustainable throughput as the primary traffic optimization target. Under
the P0 `gates/v1` amendment, the automated metric is specifically
**sustainable monitored throughput**: Ralph controls trip demand and raises it
through held stages until observed completion, accounting, backlog, recovery,
or runtime behavior reaches a versioned failure condition.

Safety, physical plausibility, fairness, and visible agreement with completion
notifications are distinct validity/review evidence. They must not be implied
by the monitored-throughput number alone.

Report both:

- Breakdown capacity: highest qualifying offered demand.
- Peak sustainable monitored throughput: highest qualifying observed
  completion rate.

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
- Finish notifications need evaluator-owned identity reconciliation and visual
  auditing against the recorded run.
- Traffic profiles yield a vector of capacities rather than one naturally
  universal value.

## Rejected alternatives

- Count anonymous vehicles passing one detector without evaluator-issued ID and
  requested-exit accounting.
- Score only a fixed low-demand scenario.
- Require literal zero queueing during rush hour.
- Combine unsafe throughput and safety penalties into one tradeable number.
