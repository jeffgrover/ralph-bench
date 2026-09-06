# ADR 0017: Require traffic validity before performance comparison

**Status:** Accepted direction; implementation proceeds in paused phases
**Date:** 2026-09-05

## Context

The operator has observed cars colliding, ignoring signals, leaving lanes, and
using implausible scale. Some local-model artifacts do not establish a traffic
simulation. The current gate ledger can accept immediate finish notifications
without observing any physical travel. The existing passing fixture proves
protocol conformance, not a physically valid intersection.

ADR 0013 made the interface easier to implement but left physical validity as
unstructured review. ADR 0014's eligibility floor can consequently be mistaken
for proof that a simulation works. The Pi proving handoff permitted by ADR
0016 also became a reduced animation assignment, which makes results from the
same named challenge incomparable.

## Decision

1. Make [TRAFFIC_CHALLENGES.md](../TRAFFIC_CHALLENGES.md) the authoritative
   traffic contract. Define the world, travelers, requested trips, dynamics,
   right of way, and evaluator-owned scenarios in plain language. These are
   behavioral concepts, not a new candidate-authored schema.
2. Require collision avoidance, signal compliance, lane discipline, realistic
   shared physical scale, and truthful trip completion throughout evaluation.
   Safety remains mandatory during overload. Publish the infrastructure
   envelope, physical bounds, and rules in the versioned public challenge.
3. Retain `gates/v1` unchanged as arrival/finish instrumentation. Its ledger
   proves accounting properties; it cannot prove physical motion or safety.
4. Report protocol conformance, traffic validity, load performance, and visual
   quality separately. Traffic validity requires explicit human review until
   independent detectors have been validated against counterexamples. Failed,
   pending, or unverifiable physical validity excludes traffic performance
   comparison; diagnostic measurements and failed artifacts remain available.
   Existing evidence-integrity and isolation requirements still apply.
5. Give every client the same complete challenge. Harness-specific execution
   instructions may describe tools and loops but may not weaken the assignment.
   Any reduced task used to calibrate tool calls is explicitly calibration,
   with distinct task identity and provenance, outside benchmark comparisons.
6. Reserve `busy-intersection/v2` for the changed contract. The dimensional
   baseline is ready for fixture calibration, not a claim of calibrated
   capacity. Activate the new public pack and scenario profile only after the
   shared prompt, acceptance/reporting path, reference/counterexamples, and
   load calibration satisfy the new requirements.
7. Use elapsed evaluation time at one world second per elapsed second. The
   current live browser worker does not deterministically advance a simulator;
   its sampling interval is not a simulation step.

Phase 1 changes documentation only. The executable v1 challenge, its public
pack, and existing result schemas remain unchanged during this phase. Later
schema changes must be versioned, old bundles must remain readable, and missing
review must never become a retrospective physical-validity pass. Store any
later human review separately, tied to the immutable run and artifact hash;
reporting remains read-only over original evidence.

## Amendments and consequences

- ADR 0013 retains the small interface and candidate implementation freedom.
  Its treatment of physical review is replaced by mandatory, evidenced traffic
  acceptance, separate from aesthetic judgment.
- ADR 0014's eligibility floor now explicitly includes physical traffic
  validity. A safe run that stalls under load can still provide a lower
  capacity measurement; a run with a physical violation cannot qualify by
  reporting good throughput from another interval.
- ADR 0016 retains the controlled/native loop distinction, tool calibration,
  evidence preservation, and feedback boundary. It no longer permits a
  reduced challenge under the same benchmark identity.
- Existing v1 results describe their original protocol/load evaluation. They
  are not evidence of satisfying v2, and their thresholds cannot be reused
  without calibration against the physical envelope.
- Human review limits comparison volume and may leave results unverifiable.
  This is preferable to inventing safety evidence from callback counts.
- The three adapter families, lifecycle cleanup, bundle validation, isolation,
  and challenge boundary remain justified. Simplification removes duplication
  and unused machinery while retaining those responsibilities.
- The city remains deferred. The Challenge Portability Fixture remains a
  boundary test, not a second production traffic challenge.

The ordered implementation and phase exit checks live in
[NEXT_STEPS.md](../NEXT_STEPS.md#refactor-phases). Pause after each phase as
requested by the operator.
