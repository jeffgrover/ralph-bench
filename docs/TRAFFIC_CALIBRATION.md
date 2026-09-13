# Human traffic review and calibration

**Status:** Implemented review validation and first signal-compliant capacity
recalibration; broader multi-model calibration remains outstanding.

The current browser worker records the evaluator-owned `gates/v1` ledger. That
ledger proves arrival identity, finish identity, timing, backlog, and recovery
accounting; it does not observe bodies, lanes, signals, or occupied space.
Human reviewers inspect the same recording and preserved artifact. Their
findings are supplied separately from the immutable bundle.

## Reference baseline (calibration only)

The evaluator-owned reference is kept in a local private reference directory,
outside the repository and staged public challenge assets. It is not a hidden
answer or a production judge. On Chromium 149 / Playwright 1.62,
seed 17, the real worker passed public smoke (6/6 travelers) and the balanced
load profile (80/80 cars, 16/16 pedestrians, zero invalid completions). The
trace observed 66 vehicles/minute at peak, first failed to keep pace at the
90-vehicle/minute offered stage, and cleared its 14-car cooldown backlog in
14,827 ms. The reference tree hash for this revision is
`0aa5b923d29a9995d88e828676ff9207ea26ade2db35c3dc2842a75fdb12c561`.
These numbers are a starting observation, not frozen thresholds;
repeat on the target platforms and complete the human review below before
activating v2.

This historical trace is retained for protocol regression only. Because its
physical behavior was not reviewed under the clarified signal rule, its high
throughput must not set the physical-capacity baseline.

## Signal-compliant recalibration — 2026-09-07

The first frontier-model artifact reviewed as visually reference-quality was
run `47b2c2f4-9dfc-4810-b296-72d42acddbbd`. Its protocol, arrival ledger,
runtime, offline, and completion-integrity checks passed. It completed 77/80
cars and 16/16 pedestrians by the 130-second horizon, while the human review
found the traffic behavior smooth, safe, and signal-compliant.

The old per-cohort completion gate was too strict for that behavior: each
20-second stage allowed only a 10-second completion grace, even though a full
signal cycle is about 33 seconds and some free-flow routes take roughly
12–14 seconds before signal or queue delay. The evaluator now treats the
30-second completion ratio as diagnostic latency evidence, and qualifies a
held stage by evaluator-owned backlog behavior instead: backlog growth may not
exceed half of that stage's newly offered cars, and total backlog remains
bounded. The 90/minute stage remains a deliberate overload probe.

Capacity reports now retain both observed peak throughput and the lower peak
among qualifying stages; completion latency includes median, P95, and maximum
car latency. These changes preserve hard protocol/runtime/traffic-validity
gates while preventing late-but-eventually-completed trips from being mistaken
for a capacity failure. Held-load and cooldown results are performance
findings, not additional validity gates: a safe, functional simulation that
stalls under overload remains eligible and is differentiated by its measured
throughput, backlog, latency, and recovery.

## Body-trace calibration — 2026-09-07

The preserved Sol and Astra artifacts were replayed with a temporary surgical
`observe` insertion so the original immutable bundles were not changed. The
full Sol trace had complete coverage and reported 24 footprint overlaps (13
car/car and 11 car/pedestrian), matching the human review's description of
quite a few collisions. The Astra trace had complete coverage
and no footprint overlaps, consistent with its human reference judgment.

Heuristic near-miss and speed-dependent-clearance categories were deliberately
removed: their encounter counts were not meaningful enough to score. Collision
evidence now produces a graduated safety score: complete trace plus zero
overlaps is `100`; each distinct collision pair halves the score; missing or
incomplete trace is unscorable. Safety is reported separately from throughput
and no longer gates whether a runnable simulation can be evaluated.

The same Sol trace retained all 24 detected overlaps when reduced from roughly
60 Hz to roughly 15 Hz (maximum gap 71 ms); reducing below the 100 ms coverage
budget missed one. New producers should therefore target 15 Hz, while Ralph
performs collision analysis after capture so detector work cannot distort the
simulation clock. The safety score is ready for calibration runs; other traffic
rules still require human review before v2 activation.

## Outcome-policy recalibration — 2026-09-08

The fresh Astra run `b84c0286-8cce-4b6c-b739-b265983f03d1` had zero detected
collisions and passed protocol, runtime, arrival, completion, and low-load
service checks. It completed 62/80 cars and left 18 cars outstanding after the
load/recovery schedule. Under the previous policy, the held-load and recovery
findings made the whole run fail. That conflated safety validity with capacity.

The evaluator now treats truthful, runnable behavior as the validity floor.
Collision observations remain immutable safety evidence, but they produce a
graduated score rather than eliminating the run: `100 * 0.5^collision_count`
for a complete trace, or unscorable when coverage is incomplete. Throughput,
backlog, latency, load breakdown, recovery, and safety score stay in the
immutable evidence and differentiate measured runs. A simulation that cannot
sustain the highest offered load, or that has imperfect safety, remains
measurable rather than disappearing from comparison.

## Sol proving run — 2026-09-08

With throughput and cooldown removed from the validity outcome, plus one bounded
repair attempt and explicit body-trace coverage feedback, Sol produced a private
simulation with a complete collision trace and zero overlaps. It completed 34/80
cars and 1/16 pedestrians, and measured 30 vehicles/minute. It remains a
performance result, not a throughput failure; the zero-collision trace earns a
100/100 safety score. The only remaining rejection was the public smoke horizon
in the immutable bundle: one car finished just after the former 12-second
post-arrival settle window. Replaying the preserved attempt-2 candidate with the
calibrated 15-second window passed all 6/6 public travelers. The original bundle
remains immutable and records the historical smoke result; a future fresh run
will seal the updated public evidence.

## Review contract: traffic-review/v2, traffic-human/v1 rubric

Run `rb review <bundle-or-run-directory>` to start the local reviewer. The
command serves only `captures/overview.webm`, `captures/overview.json`, and
`run.json`, and loads them into the page automatically. Use the timeline to
mark evidence intervals, choose an explicit status for each rule, and write
observations in plain language. The page's single file picker is only a
fallback for switching to another run.
The page locks the review before exporting JSON, preserving the exact run ID,
artifact hash, scenario, seed, coverage, per-rule timestamp references, and
optional visual-quality notes. Pass/fail/unverifiable decisions remain human
choices; sliders are context and are not converted into verdicts.

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

For `signal-compliance`, a pass means every clearly visible movement obeys the
active signal/right-of-way. A clear bypass of a controlled signal is a fail;
use unverifiable only when the signal state or movement is obscured.

Calibration note (2026-09): the first two human reviews agreed on collision,
lane, scale, and trip-integrity failures. One review marked signal compliance
pass while noting vehicles bypassed signals; that historical judgment exposed
the ambiguity and prompted the explicit rule above. Existing sidecars remain
unchanged; the clarified rule applies to subsequent reviews.

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
