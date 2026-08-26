# ADR 0013: Replace the rich traffic bridge with minimal gates

- Status: accepted
- Date: 2026-08-25

## Context

The first live Busy Intersection run produced a visually strong simulation but
could not be measured because its candidate-authored `traffic/v1` topology had
a malformed movement identity. The protocol also required network topology,
deterministic stepping, snapshots, queues, trip states, and an event ontology.
That made interface plumbing a large part of the challenge and gave one schema
mistake enough leverage to collapse an otherwise interesting artifact to an
apparent throughput of zero.

Ralph needs to control offered demand and measure completion, backlog,
load-to-failure, and recovery. It does not need to control or model the
artifact's internal traffic system.

## Decision

Replace the candidate-facing `traffic/v1` bridge with evaluator-injected
`gates/v1`:

- The artifact registers `carArrived` and `pedestrianArrived` callbacks.
- Car requests contain only evaluator ID, entrance, and requested exit.
- Pedestrian requests contain only evaluator ID, crossing, and direction.
- The artifact calls `carFinished(id, exit)` or `pedestrianFinished(id)` when a
  traveler visibly crosses its semantic finish line.
- Vehicle entrances/exits and pedestrian crossings use four cardinal semantic
  gates illustrated in the public pack; their pixel coordinates and rendering
  are not prescribed.
- Ralph owns issue/completion timestamps, validates identity/kind/exit, and
  samples issued/completed/outstanding/invalid counts throughout the run.
- The Playwright worker records that same live run. P0 physical plausibility,
  safety, and visible agreement with finish notifications are human/frontier
  visual-review dimensions rather than a candidate-authored telemetry schema.
- Page reload resets an evaluation. The static artifact may run its own demo
  behavior when `RalphGates` is absent.
- A missing gate interface is `unmeasurable`; it is not measured as zero
  throughput.

The interface is in-page JavaScript, not REST. A REST boundary would add a
server, ports, CORS, process cleanup, localhost network policy, and platform
variation without improving browser observation.

The public pack contains a small unscored smoke schedule and complete gate
contract. Production arrival mixes, rates, seeds, thresholds, and capacity
search remain evaluator-owned.

## Consequences

- Simulation architecture, clock, topology, signal policy, motion, rendering,
  and visual design remain candidate-owned.
- Ralph can derive throughput, latency, backlog, breakdown, and recovery from a
  small authoritative ledger without trusting candidate counters.
- P0 cannot independently prove collision, signal, or trajectory correctness
  from structured telemetry. The recorded run is explicit evidence for those
  judgments; stronger sensors may be added only when observed abuse justifies
  the added interface cost.
- The protocol can later add optional traveler attributes without expanding
  the v1 required surface.
- Candidate-facing portions of ADR 0003 and ADR 0009 are amended by this
  decision; their throughput and skeleton principles remain in force.
