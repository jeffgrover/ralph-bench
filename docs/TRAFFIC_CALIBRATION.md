# Human traffic review and calibration

**Status:** Implemented review validation; recorded physical calibration remains outstanding.

The current browser worker records the evaluator-owned `gates/v1` ledger. That
ledger proves arrival identity, finish identity, timing, backlog, and recovery
accounting; it does not observe bodies, lanes, signals, or occupied space.
Human reviewers inspect the same recording and preserved artifact. Their
findings are supplied separately from the immutable bundle.

## Review contract: traffic-review/v2, traffic-human/v1 rubric

Supply a JSON sidecar to `rb build --reviews <directory>`. Copy `run_id`,
`artifact_hash` (selected candidate hash), `scenario_id`, and integer `seed`
from the bundle. Include `schema_version: "traffic-review/v2"`,
`rubric_version: "traffic-human/v1"`, `reviewer`, `status`, `reason`,
`evidence_refs`, and descriptive `reviewed_intervals`.

A pass additionally requires `coverage_complete: true`, numeric `coverage_ms`
(for example `[[0, 130123]]`, in elapsed evaluation milliseconds), and a
`findings` object with all five keys: `collision-avoidance`,
`signal-compliance`, `lane-discipline`, `physical-scale`, `trip-integrity`.
Each finding needs `status: "pass"`, a nonempty `detail` explaining what was
observed, and `evidence_refs` drawn from the sidecar's top-level references.
Each rule must cite `captures/overview.webm`, optionally with a timestamp
fragment; source references can supplement the recording. References must
resolve inside the bundle. A poster alone cannot establish a pass.

Intervals must cover the entire measured evaluation without gaps, including
overload and recovery. Use `evaluation_elapsed_ms` from capture/v2 metadata;
legacy capture/v1 uses its documented planned horizon. Reviewers must reconcile
video startup offset with the evaluator timeline and mark ambiguous alignment,
occlusion, missing frames, or untraceable finishes unverifiable. Interval
validation checks the review declaration; it cannot independently establish
that the footage is sufficient. A finding of failure overrides a claimed pass.

Legacy traffic-review/v1 decisions remain readable; their weaker pass records
are unverifiable until replaced by evidenced v2 reviews. New bundle baselines
remain pending traffic-review/v1. No historical bundle is rewritten.

## Required recorded calibration cases

- a physically credible reference artifact under the public envelope;
- car/car and car/pedestrian footprint overlap;
- red-light stop-line entry;
- lane departure;
- implausible body scale;
- a finish before the whole body clears the boundary;
- movement starvation;
- held-stage backlog growth; and
- failed cooldown recovery.

Capture and review each counterexample and a safe control. Demonstrate that
reviewers can observe the violation, identify its interval, and distinguish
insufficient evidence. Fixtures for bundle/review validation can run without
model accounts; those tests do not validate visual interpretation.

## Activation work still required

The unused synthetic trace detector was removed in the closing-gaps effort:
it had no live observation producer and its passing fixture violated the
physical contract. Activating `busy-intersection/v2` still requires:

1. an evaluator-owned viable reference implementation;
2. human review calibrated against these counterexamples and deliberate
   occlusion/missing-frame cases;
3. pilot runs across the intended harness/model classes; and
4. human inspection to calibrate load, recovery, and physical thresholds.

Until those gates are satisfied, traffic review remains an explicit external
`traffic-review/v2` sidecar and performance comparison remains excluded for
pending or unverifiable physical evidence.
