# Measurement Model

**Status:** Accepted
**Date:** 2026-08-23

## Goals

The measurement model must distinguish artifact correctness, traffic-system
quality, repeated-run reliability, and the resources required by the agent. It
must not allow one dimension to conceal failure in another.

## Result dimensions

### 1. Validity

Validity answers whether the run may enter an official comparison.

Proposed validity values:

- `eligible` — required evidence and isolation policy satisfied.
- `experimental` — usable evidence but isolation or metric limitations prevent
  official comparison.
- `tainted` — verified contamination or prohibited access.
- `unverifiable` — required provenance/evidence is missing or inconsistent.

### 2. Outcome

Outcome describes the run independently of validity:

- `passed` — all critical acceptance gates passed.
- `failed` — critical gates failed.
- `partial` — run ended with a candidate but evaluation could not complete.
- `terminated` — budget, safety, inactivity, or loop protection stopped work.
- `infrastructure_error` — evaluator or provider infrastructure invalidated the
  trial.

Infrastructure errors are reported and normally excluded from model/harness
reliability denominators when the cause is demonstrably outside the SUT.

### Eligibility before performance

The primary value proposition is layered. First, the SUT must create a working
simulation that participates correctly in evaluator-owned demand. This is an
eligibility floor, not a pool of points. A candidate that does not register the
public interface, produce valid observed completions, or remain runnable is
failed, unmeasurable, or otherwise ineligible for performance comparison.

Only eligible, sufficiently evidenced artifacts receive the performance
vector: sustainable throughput, qualifying offered load, completion latency,
backlog behavior, and recovery. Higher throughput differentiates working
systems; it cannot compensate for invalid, unsafe, unverifiable, or dishonest
behavior. Resource efficiency and visual review remain separate dimensions.

The public smoke/conformance check demonstrates correct interface use. The
private judge measures performance under demand that is not fully disclosed,
so the benchmark rewards a generally working simulation rather than a
candidate tuned only to the public schedule. Relative comparisons are derived
from immutable absolute measurements at report time.

### 3. Acceptance

Assertions are structured records with:

- Stable assertion ID and challenge version.
- Severity: `critical`, `major`, `minor`, or `diagnostic`.
- Result: `pass`, `fail`, `error`, or `not_run`.
- Detector and evidence references.
- Scenario, seed, simulation interval, and threshold.

Critical failures make the artifact ineligible for a passing outcome. P0 will
show assertion coverage but will not convert regex-like implementation signals
into quality points.

### 4. Artifact performance

Traffic performance is evaluated only for structurally valid, safely runnable
artifacts. Unsafe or dishonest behavior cannot be offset by high throughput.

### 5. Agent resource efficiency

Resource metrics measure the work required to reach the first accepted
candidate, with attempt history retained.

### 6. Qualitative judgment

P0 preserves runnable artifacts and standardized captures for human judgment.
Review considers composition/layout, visual coherence, spatial legibility,
information design, motion fidelity, atmosphere/polish, originality/delight,
and whether the visuals strengthen rather than distract from the traffic
mission. A 2D intersection is not penalized merely for being 2D, and visual
quality remains separate from validity and traffic performance. Automated
frontier-model qualitative judging is deferred.

## Sustainable monitored throughput

The primary in-simulation metric is:

> Evaluator-requested cars visibly finishing at their requested gate per
> evaluation minute while the issued/completed/outstanding ledger remains
> consistent and the artifact continues serving low-load pedestrians.

A P0 `gates/v1` completion counts only when it:

- Matches an evaluator-issued ID and traveler kind.
- Is reported no more than once.
- For a car, names the requested exit gate.
- Arrives before the evaluation horizon ends.

Ralph owns issue and completion timestamps and samples its ledger throughout
the same live run recorded for review. The candidate does not provide topology,
snapshots, queues, event logs, or aggregate counters. Collision avoidance,
signal compliance, pedestrian safety, motion plausibility, and agreement
between finish notifications and visible behavior remain separate human or
frontier visual-review dimensions in P0. A missing interface produces
`unmeasurable`, not a measured throughput of zero.

## Load-to-failure protocol

### Phase structure

1. **Reset:** Reload the page and attach the injected gate monitor.
2. **Warm-up:** Low demand validates basic operation.
3. **Held stages:** Offered trip rate increases in discrete steps.
4. **Breakdown detection:** The evaluator records the first sustained failure.
5. **Refinement:** Optional fresh runs bracket the last safe and first failing
   levels.
6. **Cooldown:** New demand stops.
7. **Recovery:** The evaluator measures queue dissipation and stranded trips.

P0-A uses a bounded fixed held-stage schedule and reports the last qualifying
and first failing stages. Fresh-run bracket refinement is post-P0-A.

Held stages are preferred to a continuously changing per-frame load because
the network needs time to reveal unstable queues. A continuous ramp may be
used for the standardized visual capture.

### Offered demand versus completed throughput

The evaluator records separately:

- Issued cars and pedestrians.
- Valid car and pedestrian finishes.
- Outstanding IDs.
- Unknown, duplicate, wrong-kind, and wrong-exit notifications.
- Completion latency and observed completion rate.

An artifact cannot improve measured capacity by silently discarding demand;
every uncompleted evaluator ID remains in Ralph's outstanding ledger and
participates in breakdown and recovery evidence.

### Breakdown capacity

The highest offered demand rate that remains qualifying for the complete held
stage and recovery requirements.

```text
breakdown_capacity = highest qualifying offered cars / evaluation minute
```

### Peak sustainable monitored throughput

The highest valid completion rate observed at a qualifying load:

```text
peak_sustainable_throughput = valid car finishes / evaluation minute
```

Offered capacity and completion throughput are not interchangeable. A network
may accept demand while accumulating an unstable backlog.

### Failure classes

Immediate automated failures include:

- Missing `gates/v1` callback registration.
- Unknown, duplicate, wrong-kind, or wrong-exit finish notification.
- Low-load cars or pedestrians never receiving service.
- Browser/runtime or offline-network failure.

Sustained capacity failures include:

- Persistent visible blockage.
- Growing evaluator-owned outstanding backlog beyond the allowed window.
- Completion/service ratio below the versioned bound.
- Failure to drain outstanding demand during recovery.

Runtime failures include browser exceptions, event-loop stalls, runaway entity
growth, evaluation timeouts, and unacceptable frame/update performance.

Transient congestion does not count as immediate failure. Thresholds and
rolling windows live in versioned judge packs.

## Supporting traffic metrics

P0 derives directly from `gates/v1`:

- Issued, completed, invalid, and outstanding travelers.
- Completion rate by load stage and traveler kind.
- Median and maximum completion latency.
- First stage with sustained backlog/service failure.
- Outstanding demand at cooldown start/end and clear time.

Later protocols or calibrated visual judges may add:

- Completion rate by trip class, approach, movement, and ramp.
- Median and P95 trip time.
- Median and P95 normalized delay versus free-flow travel time.
- Maximum and time-weighted queue occupancy.
- Worst movement/approach/ramp wait.
- Stops per completed trip.
- Freeway speed as a fraction of free-flow speed.
- Grid blockage duration.
- Ramp spillback duration and evidence.
- Cooldown queue-clear time.
- Stranded trips after recovery.
- Collisions, violations, and invalid transitions.

At ordinary load—proposed initially as a fixed level near 70–80% of discovered
capacity—the evaluator reports delay, stops, fairness, and queue quality. This
prevents a design optimized only for extreme capacity from appearing uniformly
excellent.

## Scenario aggregation

Every implemented profile produces its own capacity and quality vector. P0-A
uses one canonical Busy Intersection profile across a small fixed seed set;
future city profiles and later expansions display their full vectors rather
than hiding specialization. A Challenge Portability Fixture exists to prove
that these profile-specific vectors can enter through the generic challenge
boundary; it is not itself a scored city challenge.

Candidate aggregate statistics for later calibration include:

- Median capacity across seeds.
- Worst-profile qualifying capacity.
- Harmonic mean of normalized profile capacities.
- Confidence interval or observed range.

P0 will not approve a single traffic composite. If a later product view needs
a simple summary, it must preserve the eligibility decision and the underlying
performance vector rather than allowing a weighted number to hide failure.

## Agent time measurements

All durations use monotonic evaluator-side clocks where possible. Proposed
phases include:

- Workspace preparation.
- Model/provider preparation and model load.
- Agent wall time.
- Per-attempt wall time.
- Provider request time when observable.
- Prompt-processing time when observable.
- Generation time when observable.
- Tool execution time when observable.
- Public check time.
- Private evaluation time.
- Capture and bundle time.

The primary local efficiency measure is **time to first green candidate**, not
including private judging or site generation. Cold model-load time is recorded
separately so both cold and warm operational views remain possible.

Local time comparisons require a matching hardware/provider configuration
cohort. Cross-hardware times are displayed but not ranked together by default.

## Token and throughput measurements

Store token classes separately when available:

- New uncached input.
- Cache creation/write.
- Cache read.
- Output.
- Reasoning.

Store prompt-processing and generation throughput separately. End-to-end
effective output rate may also be shown, but it is not labeled as model decode
speed.

Every metric carries provenance such as:

- `evaluator_measured`
- `provider_reported`
- `harness_reported`
- `derived_from_events`
- `estimated`
- `unavailable`

## Cloud cost measurements

Cloud cost is an evidence field, not a required numeric outcome. Ralph Bench
preserves a cost vector rather than one ambiguous number:

- Route-attributable `actual_cost_usd`, when evidenced for this run, with a
  required `actual_source`. For an OpenRouter request this is an OpenRouter
  usage debit/charge, not an upstream provider invoice.
- Generic `reference_cost_usd`, with required `reference_source`, derived from
  a frozen price snapshot, exact model mapping, and token evidence. OpenRouter
  is the canonical reference authority for the next provider slice; that
  authority is expressed in the source/UI label rather than the field name.
- Provider credits or a labeled credit equivalent, when observable.
- Explicit `status` of `complete`, `provisional`, or `unavailable`, independent
  of which amounts are populated. Actual and reference amounts may coexist;
  unavailable requires null amounts/sources and an explicit reason.

Every value is nullable and carries basis, provenance, confidence, price
snapshot/mapping version, and evidence references. Unknown is not zero. Actual
cost and reference cost are never merged into one metric or leaderboard. See
the accepted amendment in [`COST_MODEL.md`](COST_MODEL.md) and [ADR
0011](adr/0011-cloud-cost-evidence-and-openrouter-references.md).

The initial live P0 SUT uses Codex CLI with ChatGPT-managed subscription access.
P0-A does not allocate plan fees or ask for billing-period inputs. It reports
subscription cost as unavailable while preserving elapsed time, token usage
when exposed, and attempts/repair passes. After seam completion, Pi-wiggum with
a local model is the next real proving path; local cost and model-serving
configuration remain explicit provider/model evidence rather than a synthetic
cloud charge. See [`COST_MODEL.md`](COST_MODEL.md).

## Attempts and resource-to-green

Record for every attempt:

- Start/end and terminal reason.
- Prompt/feedback hash.
- Resource use.
- Candidate artifact hash.
- Public assertion result.
- Failure codes and evidence.

For a passing run, resource-to-green ends at the first candidate that satisfies
the defined acceptance gate. Later hidden evaluation remains separately timed.

Across repetitions, failed runs are right-censored at their configured budget.
The site reports pass rate, median successful resource-to-green, tail behavior,
and the count of budgeted failures. When a cohort has actual billed or
OpenRouter-equivalent reference evidence, cost-to-green may be derived with
the basis stated. P0-A subscription runs have cost unavailable, so their
time/token/attempt resource-to-green remains visible while cost-to-green is
not computed.

## P0 presentation model

P0 will expose four views:

1. **Traffic performance:** sustainable capacity and supporting quality metrics.
2. **Agent efficiency:** local time or cloud cost/reference-to-green, with
   provider-billed, OpenRouter-equivalent, credit, and unavailable values
   labeled separately when present.
3. **Pareto comparison:** resource-to-green versus sustainable throughput,
   with repeated-run reliability encoded separately.
4. **Human visual review:** runnable artifact, standardized captures, and the
   challenge's technology-neutral qualitative prompts.

The benchmark does not declare that a visually excellent but slow artifact, a
cheap adequate artifact, and an expensive high-capacity artifact are the same
kind of winner.

## Metric versioning

Every derived metric records:

- Metric ID and version.
- Challenge and judge-pack version.
- Scenario/profile and seed.
- Unit and aggregation window.
- Raw evidence references.
- Thresholds or price table used.
- Provenance and confidence/quality label.

Historical bundles are not rewritten when definitions change. The reporter may
recalculate explicitly versioned derived views from preserved raw evidence.
