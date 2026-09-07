# Closing the gaps

The previous five-phase effort is closed. This follow-up owns the review
findings and completion work; historical phase records remain available.

## Scope and exit checks

1. Remove the unused synthetic traffic detector and its misleading passing
   reference. Preserve physical counterexamples as requirements for recorded
   human-review calibration. No new candidate telemetry API.
2. Require explicit findings for collision avoidance, signals, lanes, scale,
   and trip integrity. Bind passing reviews to the scenario, seed, artifact,
   recording, and complete evaluation interval. Incomplete historical reviews
   remain readable but cannot establish a pass.
3. Require public conformance and private functional eligibility before
   comparison. Keep reduced-tool calibration and unknown policies excluded.
   Declare compatible comparison cohorts; keep official ranking disabled
   until an implemented isolation policy can establish it.
4. Reconcile usage/status documentation. Run regression tests, replay an
   existing artifact through the real browser, validate existing bundles and
   build a report, then attempt one bounded Codex/Luna evaluation.

Human review remains the implemented physical acceptance method. A credible
private reference, recorded counterexamples, calibrated load/recovery pilots,
and human findings are required before activating busy-intersection/v2.
These are outstanding benchmark validation, not completed by unit tests.

## Progress

- Engineering correction scope completed on 2026-09-07; the five-phase plan
  remains closed. Physical benchmark calibration remains outstanding below.
- Removed the unused synthetic detector; implemented scenario-bound,
  recording-backed human findings and conservative comparison eligibility.
- Regression suite: 151 tests pass. Historical artifact
  `fa18b063-dff1-4f91-8ef5-1ee1dd95d10a` passed all six public browser checks
  with no runtime/network errors. This is not proof of physical validity.
- Final report ingests four bundles with zero invalid bundles.
- One bounded Codex/Luna-high run, `1d9a0d31-b56c-4078-b069-3c426336cd57`,
  reached its 300-second model-work limit. Its preserved candidate produced a
  valid diagnostic bundle, but failed public conformance and remains excluded
  from comparison. Private load measurements alone do not establish success.
- That timeout exposed absent token usage being zero-filled. Parsers and
  aggregation now preserve unavailable/partial usage, with regression tests.
  Replaying this run's raw Codex log confirms no reported usage. Its immutable
  bundle predates the fix and retains the historical zero summary; do not
  interpret that summary as measured zero consumption or free inference.
- Added an evaluator-owned reference artifact at
  `reference/busy-intersection-v1`. The real browser worker passes its public
  smoke and full balanced load profile: 80/80 cars, 16/16 pedestrians, zero
  invalid completions, a 66 vehicles/minute observed peak, first overload at
  the 90 vehicles/minute offered stage, and recovery of all backlog in 14.8
  seconds. This establishes a reproducible protocol/load baseline only; its
  physical-validity review is still pending.

## Next validation work, in order

1. Establish a physically credible private reference and record the required
   counterexamples using the existing minimal traffic interface.
2. Calibrate load/recovery thresholds against the reference and real model
   pilots; review complete recordings with explicit per-rule findings.
3. Activate busy-intersection/v2 only after those checks support its criteria.

## Deferred enhancements

OpenRouter pricing/provider support, statistical comparison UX, city traffic,
strong isolation, and Drive ingestion follow this correction pass. Broader
macOS/Windows lifecycle validation remains a separate portability milestone.
