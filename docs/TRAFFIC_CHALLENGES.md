# Traffic Challenge Specifications

**Status:** Proposed
**Date:** 2026-08-23
**Protocol:** `traffic/v1`

## Design intent

The initial challenge family should distinguish model/harness combinations
through spatial reasoning, continuous movement, interacting state machines,
planning, debugging, optimization, and visible craftsmanship.

Both challenges produce browser-only Three.js artifacts. The evaluator owns
traffic demand, seeds, hidden profiles, checks, and captures. The submission
owns the simulation architecture, control strategy, routing strategy, geometry
within a fixed infrastructure envelope, and visual design.

The public prompt should describe the experience, constraints, evaluator
contract, and acceptance criteria. It should not prescribe filenames beyond a
single browser entry point, implementation passes, class names, global
variables, or a reference architecture.

## Shared artifact contract

### Entrypoint and runtime

- A static browser artifact with `index.html` as its entry point.
- No backend service required.
- No network dependency during evaluation.
- Pinned Three.js and evaluator bridge assets supplied by the challenge pack.
- Normal interactive playback and deterministic evaluator-driven stepping must
  operate on the same simulation state.

### Proposed evaluator API

```javascript
window.__RALPH_BENCH__ = {
  apiVersion: "traffic/v1",
  describeNetwork(),
  loadScenario(scenario),
  reset(seed),
  advance(simulatedMilliseconds),
  snapshot(),
  drainEvents()
};
```

The exact JSON schemas will be versioned. Conceptually:

- `describeNetwork()` describes nodes, directed lane segments, movements,
  signals, crossings, road classes, speed limits, and storage boundaries.
- `loadScenario()` accepts evaluator-owned trip demand and timing parameters.
- `reset()` returns the artifact to a clean deterministic state.
- `advance()` progresses simulation time without depending on display refresh.
- `snapshot()` exposes current vehicle, pedestrian, signal, queue, and trip
  state for independent checks.
- `drainEvents()` returns ordered state-transition evidence since the previous
  drain.

The evaluator does not trust self-reported summary counters without reconciling
them against requested trips, snapshots, events, and browser observations.

### Shared trip lifecycle

```text
requested -> admitted -> active -> completed
                    \-> explicitly_rejected
```

Every evaluator-requested trip must remain accounted for. A trip not yet
admitted remains in an external backlog and counts against capacity. A
submission may not silently discard, replace, shorten, or move a trip's origin
or destination.

### Shared physical constraints

Versioned challenge manifests will define:

- Fixed vehicle dimensions and collision envelopes.
- Road-class speed limits.
- Maximum acceleration and comfortable/emergency braking limits.
- Minimum following headway.
- Turning-speed or lateral-motion bounds.
- Infrastructure footprint and lane budget.
- Valid entry, exit, origin, and destination regions.

These constraints prevent throughput from being increased using tiny vehicles,
unlimited speed, teleportation, or unbounded road capacity.

## Challenge A: Busy Intersection

### Audience

Local and smaller models, with a shorter wall-time budget and several repeated
runs.

### Experience

Create a legible, living four-way signalized intersection. Vehicles approach
from all directions, travel straight or turn, form queues, respond to signals,
and exit continuously. Pedestrians request and use crosswalks. Traffic demand
rises and falls while the controller keeps the intersection safe and fair.

### Required functional scope

- Four connected approaches and exits.
- Straight, left-turn, and right-turn movements.
- Traffic signal phases with visible indications.
- Four pedestrian crossings and compatible walk phases.
- Continuous lane-following and turning motion.
- Queuing, braking, starting, and bounded vehicle spacing.
- Evaluator-supplied trip schedule and pedestrian demand.
- Pause, reset, simulation speed, and visible basic status.
- A useful default camera from which behavior is understandable.

### Infrastructure envelope

The P0 manifest will fix the footprint, maximum lanes per approach, stop-line
regions, crossing regions, vehicle dimensions, and road speed. No grade
separation is permitted. Exact lane allocation within the budget remains an
artifact design choice until calibration shows whether stronger normalization
is needed.

### Critical validity and safety checks

- Connected valid movement graph.
- Vehicles stay in declared compatible lanes and paths.
- No collisions or overlapping occupancy.
- No red-light entry.
- No vehicle/pedestrian conflict.
- No teleportation or invalid disappearance.
- Requested-trip reconciliation.
- Browser/runtime stability.

### Critical operational checks

- Every enabled vehicle movement receives service within a bounded interval.
- Pedestrians receive a compatible crossing phase within a bounded interval.
- Queues stay within the challenge storage boundary at qualifying load.
- Vehicles continue completing trips.
- The intersection drains after demand is removed.

### P0 demand profiles

1. **Balanced:** similar demand on all approaches with a representative movement
   mix.
2. **Asymmetric:** one dominant direction tests actuated behavior and fairness.
3. **Turn-heavy:** increased conflicting left turns.
4. **Pedestrian pulse:** a fixed pedestrian burst tests compatibility and delay.

P0 may score three profiles and retain the fourth as diagnostic, depending on
evaluation cost.

### Human visual questions

- Do drivers stop and start in the right places?
- Are turns and braking physically plausible?
- Can the signal state be understood immediately?
- Do pedestrians behave cautiously and legibly?
- Do queues build and dissipate like real traffic?
- Does the scene feel designed rather than assembled only to satisfy counters?

## Challenge B: The 5x5 Rush

### Audience

Frontier and cloud-class models with a larger wall-time or cost budget.

### Experience

Create a cutaway model-city traffic simulation covering a five-by-five-block
district bisected by a grade-separated freeway. City and freeway traffic must
interact through complete on- and off-ramp connections. During evaluator-owned
rush-hour profiles, queues may form but must remain contained; the network must
continue serving trips and recover after the peak.

### Required physical scope

- A five-by-five city-block district, normally formed by six street lines in
  each grid direction.
- A grade-separated through freeway bisecting the district.
- Directionally separated freeway lanes across the full scene.
- Exactly two P0 interchange areas.
- On- and off-ramp access for both freeway directions.
- One-lane P0 ramps unless the versioned manifest states otherwise.
- Local streets crossing above or below the freeway where the design permits.
- Multiple city boundary entrances and destinations.
- Signalized city intersections.
- Continuous lane following, turning, merging, and queueing.
- Visible time, speed/reset controls, and network-status information.

The model may choose interchange form, street hierarchy, signal strategy,
routing algorithm, ramp metering, merge control, building style, landscape,
camera, and visual treatment within the manifest's infrastructure limits.

### P0 exclusions

- City pedestrians.
- Parking search or curb management.
- Crashes, incidents, construction, or road closures.
- Emergency vehicles and transit priority.
- Hidden tunnels, duplicate stacked road networks, or unbounded grade
  separation.
- Sophisticated discretionary lane-changing beyond required turns and merges.

### Trip classes

The evaluator distinguishes at least:

- Freeway-through trips.
- Freeway-to-city trips.
- City-to-freeway trips.
- City-to-city trips.
- Cross-freeway local trips.

Each class receives a minimum service requirement so the artifact cannot
maximize freeway flow by effectively disconnecting the city or starving a
difficult movement.

### Critical validity and safety checks

- Connected directed road and movement graph.
- Traversable routes for every requested OD class.
- Correct freeway direction separation.
- Real ramp connections between freeway and city networks.
- Vehicles remain on valid lane/path geometry.
- No collisions, teleportation, or silent trip deletion.
- Signal and direction compliance.
- Browser/runtime stability at the required population.

### Critical operational checks

- Off-ramp queues do not spill into freeway through-lanes at qualifying load.
- On-ramp queues do not block their upstream city intersection at qualifying
  load.
- City intersections do not remain blocked by vehicles unable to clear.
- No movement, approach, ramp, or trip class is permanently starved.
- Freeway flow does not remain collapsed below its versioned threshold.
- Requested, admitted, active, completed, rejected, and backlogged trips
  reconcile.
- Critical queues dissipate during the cooldown/recovery phase.

### Meaning of "does not back up"

Zero queueing is not required. It would encourage unrealistic overbuilding and
would remove the visible rush-hour story. The requirement is **no forbidden
spillback**:

- Queues stay within designed storage at qualifying demand.
- Queues do not obstruct unrelated through movements.
- Ramp controls do not merely move gridlock from the freeway to the city.
- The system continues making progress and recovers after peak demand.

### P0 demand profiles

1. **Balanced:** mixed city, interchange, and freeway trips.
2. **Morning inbound:** freeway exits feed city destinations.
3. **Evening outbound:** city origins converge on freeway on-ramps.

Deferred profiles include asymmetric interchanges, turn-heavy cross-city
traffic, and incidents.

### Human visual questions

- Does the freeway read as a freeway and the city as a navigable district?
- Are interchange geometry, lane markings, merge behavior, and turns plausible?
- Does congestion form in understandable places?
- Can the viewer see how the controller responds?
- Do the freeway and city remain visually and behaviorally connected?
- Does the rush build, peak, and recover convincingly?
- Is the system legible at both overview and interchange camera scales?

## Standardized captures

### Intersection

- Default oblique overview.
- A canonical demand build-up and release segment.
- Optional close signal/crosswalk segment.

### City

- Wide overview across the full district.
- Closer interchange segment.
- Peak congestion segment.
- Post-peak recovery segment.

P0 may store separate short WebM captures or one chaptered capture. Captures are
derived evidence inside the run bundle, not authoritative traffic metrics.

## Public versus private material

### Public challenge pack

- Narrative prompt.
- Infrastructure constraints.
- Evaluator API schemas.
- Starter/vendor assets.
- Public smoke checks.
- One representative public scenario.

### Private judge pack

- Hidden profiles and seeds.
- Thresholds and failure windows.
- Capacity-search instructions.
- Independent cross-check configuration.
- Capture instructions.
- Reference/calibration material.

Private material must not be present in the agent workspace or public Git
repository.

## Threshold calibration

Exact vehicle counts, stage durations, speed limits, storage sizes, delay
limits, failure windows, and passing capacity thresholds are deliberately not
fixed in this planning document. They must be calibrated using:

1. Deterministic fixture artifacts.
2. At least one evaluator-owned viable implementation kept outside the public
   repository.
3. Pilot runs from several model/harness classes.
4. Visual inspection to reject technically passing but physically implausible
   behavior.

Any threshold change creates a new judge-pack version and does not silently
rewrite historical results.
