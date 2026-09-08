# Minimal collision observation design

Status: implemented collision-scoring contract, 2026-09-07. Historical bundles
remain unchanged; new measured runs use the sampled trace and binary collision
score below.

## Decision and candidate-facing contract

Add one method, `RalphGates.observe(bodies)`, to the injected JavaScript API.
Keep the existing arrival callbacks and finish notifications. The candidate
supplies occupied ground footprints; Ralph records them and computes findings.
The candidate retains its controller, motion updates, rendering and camera.

```javascript
// At roughly 15 Hz, using the same positions used to render.
RalphGates.observe([
  { id: car.id, x: car.x, y: car.y,
    length: car.length, width: car.width, heading: car.heading },
  { id: pedestrian.id, x: pedestrian.x, y: pedestrian.y,
    length: 0.6, width: 0.6, heading: 0 }
]);
```

Each call is the complete list of admitted travelers still occupying the
evaluated world. Use the evaluator-issued ID; Ralph already knows its kind.
All bodies use an oriented rectangle. Pedestrians use a small square covering
their ground footprint. No separate shapes, registration calls, handles,
candidate clocks, velocities, collision flags or aggregate counters.

| Field | Meaning |
|---|---|
| `id` | Unchanged evaluator-issued traveler ID |
| `x`, `y` | Ground-plane center, in meters; east and south positive; junction center is `(0, 0)` |
| `length`, `width` | Full occupied dimensions in meters; length runs along heading |
| `heading` | Radians clockwise from east; zero is east, pi/2 is south |

Use one fixed conversion if internal coordinates are pixels or other units.
2D, isometric and 3D renderers report the underlying ground plane before camera
projection. Heading describes the body, including during turns. Footprints
cover the visible physical body, excluding shadows, labels and decorative
outlines. Dimensions are fixed per traveler and respect the public challenge
bounds. This design covers the at-grade intersection; multiple road elevations
in the future city challenge need their own extension.

Screen-space pixels were rejected because zoom, perspective and resolution
would change the apparent clearance, and projected bodies can overlap without
physical contact. Meters reuse the planned challenge's physical envelope and
let the same safety margin apply to every model. Arbitrary polygons would add
validation and implementation work without a demonstrated intersection need.

## Reporting lifetime and cadence

- Before admission, an issued traveler may be absent. Ralph already counts it
  as outstanding demand. First appearance establishes admission.
- Report immediately after spawning and then at a steady cadence of roughly
  15 observations per second (target every 60–70 ms; never slower than 10 Hz).
  The model may update its own motion at animation-frame frequency; body
  observation is a sampled evidence stream, not a second simulation clock.
- Once admitted, a traveler must appear in every report until it has fully
  cleared its finish boundary. Include the final footprint before the existing
  finish notification; removal may follow that notification. Call order makes
  that boundary explicit even when everything occurs within one browser frame.
- A finished traveler still physically in the world remains in observations
  and collision checks. Completion must never exempt a visible body.
- A body disappearing before completion, reappearing after removal, changing
  dimensions, duplicating an ID, or finishing without any observed body is an
  evidence-integrity violation. No incidental demo traffic during evaluation;
  all bodies must correspond to evaluator-issued arrivals.

Ralph copies and validates numeric values on receipt, adds its monotonic time
and sequence number, and preserves order. It must not retain mutable candidate
objects. Cap body count, report frequency, trace size and processing work;
exceeding a cap produces an explicit evidence failure, never silent dropping.
Budgets and tolerances belong to the versioned observer configuration.

The initial calibration target is 15 observations per elapsed second; flag gaps
exceeding 100 ms. These are coverage settings, not physical safety thresholds.
Receipt times within a synchronous batch do not establish the duration of
physics substeps. The evaluator may analyze the sampled trace in a separate
post-run process; it must not let detector work distort the simulation clock.

## What Ralph computes

**Contact/overlap:** compare oriented rectangles for car/car and
car/pedestrian pairs. Use axis-aligned extents only as a cheap rejection test;
the final check must account for heading. Define a small numerical tolerance
and an uncertain boundary band so roundoff cannot become an invented collision.
Pedestrian/pedestrian spacing is outside the first detector's scope.

**Collision score:** compare oriented rectangles for car/car and
car/pedestrian pairs. A complete, valid trace with zero overlaps scores `1`; a
trace with one or more overlaps scores `0`; unavailable or incomplete evidence
is unscorable. This is intentionally binary. Do not infer safety from distance,
speed, heading, or a heuristic safety envelope.

**Between observations:** test motion between consecutive samples using a
bounded sweep of interpolated centers and headings, including angle wraparound.
An overlap found by that sweep is counted as contact under this evaluator
model. Gaps beyond the coverage limit make the overall collision score
unscorable; they do not become a guessed pass. Straight interpolation cannot
prove what an arbitrary unreported curved path did, so the cadence and coverage
contract remain part of the score.

Group repeated contacts for the same pair into one encounter, with start/end
times and evidence sample references. Preserve the raw trace so the collision
detector can be re-scored without another model generation or mutation of the
original bundle.

## Evidence and trust

This is an independent calculation over candidate-reported geometry. It
catches errors even when the candidate has no collision checker, but a
candidate can still omit or falsify geometry. IDs, dimensions, cadence and
lifetime checks catch some discrepancies; they cannot establish that the
renderer used the reported positions. Detector accuracy tests cannot remove
this trust limitation.

Provide an evaluator-generated top-down footprint replay with IDs and flagged
encounters alongside the existing recording. A reviewer can compare positions,
body sizes and motion and seek directly to a reported event. Reuse the review
page; the candidate needs no debug renderer or camera-projection API. Align
the trace and recording using a measured capture offset; do not assume their
time zero is identical. Perspective may make correspondence unverifiable.

The initial report distinguishes observed contact, missing evidence, and no
detected contact. A complete zero-contact trace earns the automated collision
score; any contact vetoes load-comparison eligibility. Preserve human review for
geometry/rendering agreement, signals, lanes and trip integrity. A detector
disagreement requires inspection of the paired trace and video. Safety cannot
be traded against throughput, including during overload.

## Small implementation path

1. Keep `gate_bridge.py` as a cheap in-page sampler with observation validation
   and bounded buffering. Drain the trace through a separate post-run analysis
   step; the Playwright worker must not perform detector work for every body
   update.
2. Add one pure geometry/encounter evaluator. Start with pairwise scans and
   a cheap bounds rejection; measure overhead before adding spatial indexing.
   Persist trace and findings through the challenge's existing evidence path,
   keeping traffic logic out of the conductor.
3. Add event links and the simple top-down trace replay to the existing review
   workflow. Ensure unsafe runs display no eligible throughput, even if their
   historical machine/load outcome says passed.
4. Exercise actual browser producers and geometry tests, then publish the
   required method in a new versioned public challenge pack. Old v1 bundles
   remain readable with collision evidence unavailable. Replaying an old
   artifact with an added adapter is a new calibration run, not retrospective
   evidence about its original recording.

This narrowly amends ADR 0013's prohibition on candidate snapshots: a body
observation is now justified by observed collision failures. It does not add
topology, queues, signals, stepping commands or a general simulation ontology.
Update that ADR and repository guidance when the design is implemented.

## Validation and estimate

Use real reported positions, not preset fixture verdicts. Required cases:
rotated cars colliding during a turn; car/pedestrian contact; fast crossing
between samples; two paths crossing at different times; safe adjacent lanes;
pedestrian/pedestrian exclusion; heading wraparound;
spawning overlap; missing/late reports; disappearing and falsely finished IDs;
and mismatched rendering/telemetry. Repeat equivalent motion with a resized 2D
view and a perspective view: geometric findings must remain the same. Measure
observer overhead under the busiest scenario so it does not distort capacity.

Estimate: 2–3 engineering days for the narrow producer, sampled-contact checks,
raw evidence and meaningful tests; another 2–3 for bounded sweep handling,
review integration and real-browser calibration. Treat this as roughly 4–6
days for the useful integrated slice, with coverage validation dependent on
reviewer availability. The previous 2–4 day estimate understated the sweep
and evidence work. Acceptance requires an end-to-end recorded fixture with
correct findings, explicit coverage limits, and a small candidate integration
example; automatic safety certification is not an exit criterion.
