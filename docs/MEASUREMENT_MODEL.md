# Measurement Model

**Status:** Proposed
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

## Sustainable valid throughput

The primary in-simulation metric is:

> Valid, evaluator-requested trips completed per simulated hour while all
> qualifying safety, accounting, fairness, queue-containment, and recovery
> constraints remain satisfied.

A trip counts only when it:

- Matches an evaluator-issued trip ID, origin, destination, and departure
  request.
- Is admitted and represented in snapshots/events.
- Traverses connected valid movement geometry.
- Does not teleport or disappear outside a valid completion region.
- Respects direction and applicable controls.
- Completes before the evaluation horizon.

## Load-to-failure protocol

### Phase structure

1. **Reset:** Clean state and fixed seed/profile.
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

- Requested/offered trips.
- Admitted trips.
- External backlog.
- Active trips.
- Completed trips.
- Explicitly rejected trips.
- Lost or inconsistent trips.

An artifact cannot improve capacity by delaying admission indefinitely or
discarding demand. External backlog participates in failure criteria.

### Breakdown capacity

The highest offered demand rate that remains qualifying for the complete held
stage and recovery requirements.

```text
breakdown_capacity = highest qualifying offered trips / simulated hour
```

### Peak sustainable throughput

The highest valid completion rate observed at a qualifying load:

```text
peak_sustainable_throughput = valid completed trips / simulated hour
```

Offered capacity and completion throughput are not interchangeable. A network
may accept demand while accumulating an unstable backlog.

### Failure classes

Immediate transport failures include:

- Collision or prohibited overlap.
- Vehicle/pedestrian collision.
- Red-light or direction violation.
- Teleportation or invalid traversal.
- Lost/duplicated trip identity.

Sustained capacity failures include:

- Queue storage overflow or forbidden spillback.
- Persistent blocked intersection.
- Starvation above a versioned wait limit.
- Growing internal or external backlog beyond the allowed window.
- Completion/service ratio below the versioned bound.
- Persistent freeway speed collapse.
- Failure to drain critical queues during recovery.

Runtime failures include browser exceptions, event-loop stalls, runaway entity
growth, invalid snapshots, evaluation timeouts, and unacceptable frame/update
performance.

Transient congestion does not count as immediate failure. Thresholds and
rolling windows live in versioned judge packs.

## Supporting traffic metrics

- Requested, admitted, active, completed, rejected, and outstanding trips.
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
P0-B and later profile expansions display the full vector rather than hiding
specialization.

Candidate aggregate statistics for later calibration include:

- Median capacity across seeds.
- Worst-profile qualifying capacity.
- Harmonic mean of normalized profile capacities.
- Confidence interval or observed range.

P0 will not approve a single traffic composite until pilot distributions are
available.

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

Cost is mandatory for every cloud result. Ralph Bench preserves a cost vector
rather than one ambiguous number:

- Provider-billed USD, when attributable.
- Marginal cash or purchased-credit charge, when observable.
- Allocated flat-subscription USD.
- Provider credits or a labeled credit equivalent.
- Token-derived API list-price equivalent with a versioned price table.

Every value is nullable and carries basis, provenance, confidence, policy/rate
version, and evidence references. Unknown is not zero. An official cloud cost
comparison requires complete evidence and a non-null primary USD cost under a
declared policy.

The live P0 SUT uses Codex CLI with ChatGPT-managed subscription access. P0
implements `flat-subscription-attempt-pool/v1`: the operator declares the USD
amount one experiment should bear, and a closed catalog pool allocates it using
chargeable model-attempt counts. Passing, failing, tainted, aborted, and
post-generation infrastructure outcomes consume cost. Marginal cash, raw
usage, provider credits, and API list-price equivalent remain separate
secondary fields.

The P0 UI calls this value **allocated subscription USD per chargeable
attempt/task**. It is a declared accounting allocation, not a provider-reported
request price. Primary cost rankings require the same mechanical comparability
key; incompatible policies/source classes appear in separate cohorts.

Open pools may show provisional allocation but do not enter a final cost
ranking. P0 uses fixtures for metered APIs and missing/incomplete cost rather
than implementing another live provider. See [`COST_MODEL.md`](COST_MODEL.md).

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
and the count of budgeted failures. Cloud cost-to-green includes the allocated
or billed cost of failed trials; it may not compute a successful-only mean that
makes failed work economically disappear.

## P0 presentation model

P0 will expose four views:

1. **Traffic performance:** sustainable capacity and supporting quality metrics.
2. **Agent efficiency:** local time or policy-compatible cloud cost to green,
   with allocated, marginal, credit, and equivalent values labeled separately
   when present.
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
