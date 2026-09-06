# Traffic Challenge Specifications

**Status:** Accepted direction, amended by [ADR 0017](adr/0017-traffic-validity-before-performance.md)
**Updated:** 2026-09-05
**Executable challenge:** `busy-intersection/v1`, using `gates/v1`.
**Refactor target:** `busy-intersection/v2`, retaining `gates/v1`.

The Busy Intersection requirements below define the v2 target. They are not
implemented acceptance checks yet. The v1 public pack, registry, evaluator,
and historical results retain their original meaning until the staged
[refactor](NEXT_STEPS.md#refactor-phases) is complete. A current `passed` or
`performance_eligible` result does not establish physical traffic validity.

## Design intent

The initial challenge family should distinguish model/harness combinations
through spatial reasoning, continuous movement, interacting state machines,
planning, debugging, optimization, and visible craftsmanship.

Both challenges produce browser-only visual artifacts. The city is intended as
a grand spatial showcase, while the intersection may use a polished 2D, 2.5D,
or 3D presentation. A rendering technique is not inherently superior: a
beautiful, lucid top-down design may be more successful than an awkward 3D
scene. The evaluator owns traffic demand, seeds, hidden profiles, checks, and
captures. The submission owns the simulation architecture, control strategy,
routing strategy, geometry within a fixed infrastructure envelope, and visual
design.

Delivery is intentionally staged. P0-A completes the Busy Intersection
evaluator and adds a **Challenge Portability Fixture** on the same generic
challenge boundary. The fixture proves that another challenge can be
registered, materialized, evaluated, captured, and bundled without
Busy-specific conductor branches. It is not a partial city simulation. A
future city evaluator and profile may define its own versioned topology,
protocol, and measurement objects through the challenge adapter without being
limited by the intersection's four-gate vocabulary.

The public prompt should describe the experience, constraints, evaluator
contract, and acceptance criteria. It should not prescribe filenames beyond a
single browser entry point, implementation passes, class names, global
variables, or a reference architecture.

## Traffic model

A traffic simulation moves finite bodies through shared space over time,
subject to geometry, other travelers, and right of way. Moving sprites or
acknowledging requests is insufficient. These terms describe required
behavior; they are not additional API objects or prescribed code classes.

| Term | Meaning and owner |
|---|---|
| World | Roads, directed lanes, permitted turning paths, stop lines, crosswalks, and sidewalks in meters. The challenge bounds the infrastructure; the artifact implements it. |
| Traveler | A car or pedestrian with an occupied footprint, position, direction, and motion. The artifact maintains one continuous traveler for each admitted request. |
| Trip request | Evaluator-issued identity and destination. A request remains outstanding while waiting to enter and while traveling. |
| Dynamics | Motion constrained by available space, speed limits, other travelers, and signals. The artifact chooses its algorithms. |
| Right of way | Permission to enter a movement or crossing. Permission never allows a collision or entry into a blocked exit. |
| Scenario | Evaluator-owned arrivals, timing, load stages, and recovery demand. The artifact cannot select or discard its workload. |

A request waits outside the modeled road until entry space is available; it
must not spawn on another traveler. Once admitted, it occupies road or
crosswalk space until its whole footprint reaches the requested destination.
An on-road queue contains actual bodies. Ralph's **outstanding demand** also
includes requests waiting to enter; it is not a measurement of queue length.
No request may be silently dropped, teleported, or acknowledged without travel.

## Required traffic validity

Every rule applies during warm-up, held load, overload, and recovery. Overload
may increase waiting and reduce service; it never relaxes these requirements.

| Requirement | Passing behavior | Deliberate counterexample |
|---|---|---|
| Collision avoidance | Car bodies never contact or overlap other cars or pedestrian footprints, including during spawning, turns, braking, and queues. Separate center points are insufficient. | Crossing cars intersect; a turning car passes through a pedestrian. |
| Signal compliance | Cars obey the movement signals and stop lines; pedestrians obey crossing phases. Visible signals govern actual motion. | A car enters on red while an unrelated signal animation changes color. |
| Lane discipline | The whole car follows its directed lane or a continuous permitted turn into the correct receiving lane. | A car cuts over a sidewalk, crosses into opposing approach traffic, or changes position to bypass a queue. |
| Physical scale | Rendered bodies, occupied footprints, lane geometry, and motion share the public physical units and bounds below. | Tiny collision bodies under large sprites, shrinking cars under load, or oversized lanes. |
| Trip integrity | Each accepted finish corresponds to the full requested trip in the evaluated world. | The callback immediately reports completion, or a car disappears before reaching its exit. |

An observed violation fails traffic validity regardless of throughput or
appearance. Absence of a detected violation is not automatically a pass.
Evidence that cannot establish the required behavior remains pending or
unverifiable under the [measurement model](MEASUREMENT_MODEL.md#eligibility-before-performance).

## Shared artifact contract

### Entrypoint and runtime

- A static browser artifact with `index.html` as its entry point.
- No backend service required.
- No network dependency during evaluation.
- The evaluator injects the dependency-free `RalphGates` JavaScript interface;
  the artifact does not run a server or bundle evaluator code.
- Any supplied dependency the candidate uses must be copied into the final
  static submission so the bundle remains runnable without the challenge
  source tree or a network.
- Ralph monitors and records the same live page run. The artifact may provide
  any standalone demonstration behavior when `RalphGates` is absent.

### Minimal gates API

```javascript
RalphGates.register({
  carArrived({ id, entersFrom, exitsTo }) { /* retain request; admit when safe */ },
  pedestrianArrived({ id, crossing, direction }) { /* retain request; admit when safe */ }
});

RalphGates.carFinished(id, exit); // whole car has cleared the requested exit
RalphGates.pedestrianFinished(id); // whole pedestrian has reached the far sidewalk
```

Vehicle entrances and exits are `north`, `east`, `south`, and `west`; evaluator
requests never contain a U-turn. North/south pedestrian crossings use
`east-to-west` or `west-to-east`, while east/west crossings use
`north-to-south` or `south-to-north`. The public pack includes an SVG defining
these semantic gates without fixing their pixel coordinates or visual style.

Ralph owns arrival IDs and timestamps. It accepts a finish only for a known ID,
only once, and for cars only at the requested exit. It samples its issued,
completed, outstanding, invalid, and latency ledgers throughout the same live
run captured for visual review. Page reload is the reset boundary.

There is no candidate-authored network description, topology schema, snapshot,
queue report, summary counter, simulation clock, or parallel event ontology in
`gates/v1`. Those concepts remain implementation choices inside the artifact.

### Visual design and creative latitude

Visual quality is an explicit human-interpretation dimension, not a decorative
afterthought. The artifact should feel intentionally designed from its overall
composition down to controls, typography, color, motion, and small feedback
details. It should invite a person to watch the traffic story unfold and make
the system understandable before they inspect any numeric results.

The submission has broad freedom to surprise and delight. It may choose a
realistic, schematic, low-poly, illustrated, architectural-model, control-room,
playful, or otherwise distinctive visual direction. Creative latitude includes:

- Overall layout, composition, framing, and use of space.
- Color system, typography, iconography, materials, lighting, and atmosphere.
- Vehicle and pedestrian styling, environmental details, and visual identity.
- Camera or viewport behavior, transitions, animation, and interaction.
- Information hierarchy, overlays, legends, selection states, and controls.
- Visual explanations of demand, queues, signal state, routing, throughput,
  congestion, and recovery.

These are opportunities rather than a required asset checklist. A coherent
minimal design can be more compelling than a busy one. The prompt should not
dictate a palette, dashboard layout, camera rig, building style, or aesthetic
theme.

The main mission remains traffic simulation. Visual ambition must not:

- Obscure lane geometry, signal state, queue boundaries, or unsafe behavior.
- Misrepresent evaluator-observed state or substitute animation for simulation.
- Make labels, controls, or critical distinctions unreadable.
- Depend only on color where shape, position, iconography, or text is needed.
- Reduce browser stability or traffic population below challenge requirements.
- Turn the interface into a dashboard that overwhelms the traffic itself.

The artifact will be viewed at standardized desktop dimensions and in recorded
captures, so responsive composition, contrast, visual hierarchy, and behavior
at the capture viewpoint matter. Visual fidelity is judged independently of
traffic validity and throughput; it cannot rescue an invalid simulation, and a
technically excellent simulation does not automatically count as visually
excellent.

### Evaluator-owned completion ledger

```text
issued -> outstanding -> finished
```

Every evaluator request remains outstanding until its finish notification.
Silently dropped demand therefore becomes visible backlog. Ralph computes
throughput and latency from its own timestamps rather than candidate counters.
An artifact that does not register the two callbacks is `unmeasurable`, not a
zero-throughput simulation.

### What gates establish

The ledger validates identity, kind, destination, uniqueness, and notification
timing. It cannot establish that a body traveled, avoided a collision, stayed
in a lane, obeyed a signal, or used realistic dimensions. Physical constraints
belong to the challenge revision; retaining `gates/v1` does not waive them.
Candidate counters, scale labels, and claims are not independent verification.

## Challenge A: Busy Intersection

### Audience

The same traffic task applies to local and cloud models. Model-work budgets
and client tool policies are explicit experiment settings. A limited local
model receives the complete challenge and an honest failure or incomplete
result if it cannot satisfy it. Adapter-specific handoffs must not replace the
simulation with a smaller animation assignment.

### Experience

Create a legible, living four-way signalized intersection. Vehicles approach
from all directions, travel straight or turn, form queues, respond to signals,
and exit continuously. Pedestrians request and use crosswalks. Traffic demand
rises and falls while the controller keeps the intersection safe and fair.

The presentation may be 2D, 2.5D, or 3D. A top-down graphic can lean into
clarity, information design, and beautiful motion; a 3D scene can lean into
physical presence, depth, environment, and cinematic observation. Neither
choice receives an automatic preference. The artifact should use its chosen
medium confidently and make the intersection feel like a complete designed
experience rather than a debugging canvas.

### Required functional scope

- Four connected approaches and exits.
- Straight, left-turn, and right-turn movements.
- Traffic signal phases with visible indications.
- Four pedestrian crossings and compatible walk phases.
- Continuous lane-following and turning motion.
- Queuing, braking, starting, and bounded vehicle spacing.
- Evaluator-supplied car and pedestrian arrival callbacks.
- Visible basic status; optional demo controls obey the evaluation-time rules
  below.
- A useful default view from which behavior is understandable.

### Visual opportunity

The intersection is a compact composition in which polish will be easy to see.
Possible avenues for differentiation include thoughtful road and crosswalk
markings, sidewalks and environmental context, expressive but legible vehicles
and pedestrians, beautifully timed signal feedback, satisfying turning and
queue motion, an integrated control surface, and concise live information.

The artifact should communicate at a glance:

- Which movements currently have right of way.
- Where demand and queues are building.
- How the intersection is responding.
- Whether the traffic system is coping as load rises.
- What changed during peak and recovery.

The information layer may be restrained or sophisticated, but it should share
the artifact's visual language rather than look like unrelated developer
instrumentation.

### Infrastructure envelope

These are the public v2 baseline for fixture calibration. They are benchmark
choices, not a claim to reproduce every road or vehicle. Freeze them in the
v2 public pack before activation; do not reuse v1 load thresholds without
calibration. Changes after activation require a new challenge revision.

| Property | Baseline and allowed variation |
|---|---|
| Modeled footprint | 120 m by 120 m, centered on one at-grade four-way intersection. Four vehicle entrance/exit gates lie at the road ends on the boundary, 60 m from the center. Decorative scenery cannot add road storage. |
| Lane budget | Right-hand traffic; one inbound and one outbound lane on each approach. No extra turn lanes, bypasses, grade separation, or hidden roads. |
| Lane width | 3.3 m nominal; 3.2–3.4 m allowed. Width is the usable travel lane, excluding sidewalks and decorative shoulders. |
| Car body | 4.6 m long by 1.8 m wide nominal; length 4.4–4.8 m and width 1.7–1.9 m allowed. The collision footprint covers the visible body. |
| Pedestrian footprint | A ground footprint at least 0.6 m across. Car/pedestrian separation uses this occupied space, not a point. |
| Crossing and stop-line regions | One marked crosswalk across each approach, centered 8–12 m from the junction center and 3 m wide along the road. Stop lines lie 14–18 m from the center, before the crosswalk in the incoming direction. |
| Speed bounds | Cars at most 30 km/h (approximately 8.33 m/s), at most 15 km/h (approximately 4.17 m/s) through turns; pedestrians at most 1.4 m/s. Stopping and queuing are expected. |

The car baseline is rounded from a production sedan: Toyota's 2022 Corolla
saloon specification lists 4,630 mm length and 1,780 mm width.
[Toyota technical specification, p. 4](https://media.toyota.co.uk/wp-content/uploads/sites/5/pdf/220111M-Corolla-Tech-Spec.pdf).
The lane range fits within the 10–12 ft (3.048–3.658 m) range described in
[FHWA's Road Diet Informational Guide, section 4.1.4](https://highways.dot.gov/safety/other/road-diets/road-diet-informational-guide/4-designing-road-diet).
The tolerances, footprint, lane budget, pedestrian footprint, crossing regions,
and speed caps are benchmark selections to be exercised by the reference
fixture, not values mandated by those sources.

Choose dimensions within these bounds once per artifact; do not change them
with load. Use one meter scale for visible geometry, occupied bodies, and
motion. Perspective and pixel scale remain free. Provide a readable ground
scale reference and a view that permits review of lanes, bodies, stop lines,
signals, and all crossings. Review must corroborate scale with geometry and
preserved implementation evidence; printing a plausible scale label is
insufficient. Curves must fit the entire car, not just its center point.
Frame the boundary gates with enough visual margin to observe a whole body
entering or clearing the world; that margin provides no additional road
storage.

### Right of way and motion

These simplified benchmark rules are shared by every candidate:

- Red forbids new entry beyond the stop line, including right turns. A car
  already lawfully inside the junction may clear it.
- Green permits the indicated movement only when the path and receiving lane
  have room. Turning traffic yields to conflicting travelers already entitled
  to proceed. A green light does not grant unconditional entry.
- Yellow permits clearing; an approaching car must stop if it can do so
  without abrupt or unsafe braking. Otherwise it may continue to clear.
  Release no conflicting movement until previous traffic has cleared.
- Pedestrians start crossing only during WALK and may finish after WALK ends.
  Vehicles must yield to pedestrians still crossing; a new vehicle phase must
  not strand or endanger them.
- Vehicles follow continuous forward paths with plausible acceleration,
  braking, and turning. No jumps, instant reversals, lane shortcuts, passing
  through bodies between frames, or speed multipliers under load.

The artifact chooses phase order, durations, protected turns, and control
strategy within these rules. A simple controller is sufficient if every
requested movement and crossing receives service at qualifying demand.

### Evaluation time

One world second corresponds to one elapsed evaluation second. Ralph schedules
arrivals and records completion times using monotonic elapsed time while
recording the same live browser run. The artifact owns its update loop; it
must not accelerate traffic to inflate completions. Demo pause, speed, and
reset controls must not alter an evaluated run. Page reload starts a new run.

Ledger sampling and captured frame rate are observation intervals, not
simulation steps. The current browser worker does not provide deterministic
fast-forward simulation. Slow or missing frames limit the evidence; they do
not authorize teleportation or a claim that hidden motion has been verified.

### Automated measurement checks

- Arrival callbacks register successfully.
- Issued IDs, completion IDs, and requested car exits reconcile.
- No unknown, duplicate, wrong-kind, or wrong-exit completion.
- Low-load cars and pedestrians produce valid finish notifications.
- Outstanding demand, completion latency, throughput, breakdown, and recovery
  remain observable through the evaluator-owned ledger.
- Browser/runtime stability.

These checks establish protocol/runtime conformance and demand accounting.
They do not establish the required traffic validity above.

### Traffic review and evidence

Until an independent detector is validated against the corresponding
counterexamples, require an explicit human traffic review for each evaluated
run. Preserve the artifact hash, scenario and seed, ledger, and the recording
of that same run. Review records identify the reviewer, rubric version,
coverage, finding for each required rule, and supporting capture timestamps or
artifact evidence. Later review belongs outside the immutable run bundle.

Review covers entry, queuing, straight and turning movements, all crossings,
signal transitions, finishes, and the load/recovery intervals being reported.
A poster, a few attractive frames, source inspection alone, candidate claims,
or a different demo run cannot establish those behaviors. If resolution,
occlusion, missing intervals, or ambiguous traveler/finish correspondence
prevents a finding, record it as unverifiable. A review pass means the stated
rubric and coverage were satisfied; it is not a mathematical proof of all
unobserved states. Automated frontier judging remains deferred.

The existing passing fixture demonstrates protocol conformance only. A
credible evaluator-owned reference and deliberately broken fixtures must
exercise the observation method for every rule before v2 comparisons begin.
See [measurement and eligibility](MEASUREMENT_MODEL.md#eligibility-before-performance).

### Critical operational checks

- Every enabled vehicle movement receives service within a bounded interval.
- Pedestrians receive a compatible crossing phase within a bounded interval.
- Queues stay within the challenge storage boundary at qualifying load.
- Vehicles continue completing trips.
- The intersection drains after demand is removed.

### Demand profile ladder

1. **Balanced:** similar demand on all approaches with a representative
   movement mix. This is the initial v2 calibration target, across a small
   fixed seed set.
2. **Asymmetric:** one dominant direction tests actuated behavior and fairness.
3. **Turn-heavy:** increased conflicting left turns.
4. **Pedestrian pulse:** a fixed pedestrian burst tests compatibility and delay.

The other profiles remain calibration cases until separately validated and
versioned for comparisons. A list of proposed profiles is not evidence of an
implemented or calibrated production judge.

### Human visual questions

- Does the artifact have an appealing and distinctive visual identity?
- Do layout, spacing, palette, typography, and controls feel intentional?
- Is the chosen 2D, 2.5D, or 3D treatment used effectively?
- Can the signal state be understood immediately?
- Is the traffic information useful without becoming cluttered or dominant?
- Are motion, transitions, and feedback satisfying to watch?
- Does the scene feel designed rather than assembled only to satisfy counters?
- Is there a memorable detail or overall sense of craft that creates a genuine
  "wow" response?

## Challenge B: The 5x5 Rush

The 5x5 Rush remains a future city challenge, not the P0 portability fixture.
Its implementation is intentionally open until the generic challenge boundary
is complete and the city-specific requirements are understood.

### Audience

Frontier and cloud-class models with a larger wall-time or cost budget.

### Experience

Create a cutaway model-city traffic simulation covering a five-by-five-block
district bisected by a grade-separated freeway. City and freeway traffic must
interact through complete on- and off-ramp connections. During evaluator-owned
rush-hour profiles, queues may form but must remain contained; the network must
continue serving trips and recover after the peak.

This is the grand visual challenge. The city should reward spatially coherent
3D or richly dimensional presentation at overview and interchange scales. It
should make a technically complex network inviting to explore, let the viewer
follow individual and system-wide behavior, and provide a strong sense of
place. Visual ambition is encouraged as long as the freeway, ramps, streets,
signals, vehicles, congestion, and control response remain legible.

### Required physical scope

- A five-by-five city-block district, normally formed by six street lines in
  each grid direction.
- A grade-separated through freeway bisecting the district.
- Directionally separated freeway lanes across the full scene.
- Exactly two P0-B interchange areas.
- On- and off-ramp access for both freeway directions.
- One-lane P0-B ramps unless the versioned manifest states otherwise.
- Local streets crossing above or below the freeway where the design permits.
- Multiple city boundary entrances and destinations.
- Signalized city intersections.
- Continuous lane following, turning, merging, and queueing.
- Visible time, speed/reset controls, and network-status information.

The model may choose interchange form, street hierarchy, signal strategy,
routing algorithm, ramp metering, merge control, building style, landscape,
camera, and visual treatment within the manifest's infrastructure limits.

### Visual opportunity

The city offers room for a model to establish an original art direction and
then apply it consistently across a much larger system. Possibilities include a
model-railway or architectural-diorama treatment, a clean planning
visualization, a warm lived-in city, a dramatic day-to-evening rush, or another
coherent interpretation.

Visual craft may appear in buildings and skyline rhythm, block composition,
bridges and ramp structures, lane markings and signage, vegetation and public
space, vehicle variety, shadows and lighting, head/tail lights, camera
transitions, congestion emphasis, route selection, or a carefully integrated
operations display. None of these individual features is mandatory.

The presentation should help a viewer move between scales:

- Read the whole network and the freeway's relationship to the grid.
- Understand an interchange's lanes, merges, queues, and storage.
- Follow selected trips without losing the system-wide story.
- See rush-hour demand build, reach the network's limit, and recede.
- Understand why the first breakdown occurred and whether recovery succeeded.

Information design is particularly important at city scale. Status, charts,
legends, highlights, and labels should reveal the simulation rather than cover
it. The traffic remains the primary visual subject.

### P0-B exclusions

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

### P0-B demand profiles

1. **Balanced:** mixed city, interchange, and freeway trips.
2. **Morning inbound:** freeway exits feed city destinations.
3. **Evening outbound:** city origins converge on freeway on-ramps.

Deferred profiles include asymmetric interchanges, turn-heavy cross-city
traffic, and incidents.

### Human visual questions

- Does the city have a cohesive, attractive, and distinctive art direction?
- Are composition, color, lighting, typography, controls, and information
  hierarchy consistently resolved?
- Does the freeway read as a freeway and the city as a navigable district?
- Are interchange geometry, lane markings, merge behavior, and turns plausible?
- Does congestion form in understandable places?
- Can the viewer see how the controller responds?
- Do the freeway and city remain visually and behaviorally connected?
- Does the rush build, peak, and recover convincingly?
- Is the system legible at both overview and interchange camera scales?
- Can a viewer inspect detail without losing the larger traffic narrative?
- Does visual richness support rather than obscure simulation performance?
- Is the result polished, memorable, and capable of producing a genuine
  "wow" response?

## Standardized captures

### Intersection

- Default full-layout view appropriate to the chosen 2D, 2.5D, or 3D treatment.
- A canonical demand build-up and release segment.
- An overview poster from the same artifact/scenario.

This single overview animation/poster pair is the P0-A capture profile. A
closer signal/crosswalk segment is optional after P0-A.

### City

- Wide overview across the full district.
- Closer interchange segment.
- Peak congestion segment.
- Post-peak recovery segment.

These are P0-B requirements. P0-B may store separate short WebM captures or one
chaptered capture. Captures are derived evidence inside the run bundle, not
authoritative traffic metrics.

## Subjective human visual interpretation

P0 will not ask an automated model judge to convert visual quality into a
supposedly objective number. It will foreground the runnable artifact and
standardized captures alongside measured demand results and the explicit
traffic-validity review. Aesthetic review does not replace that required
review.

The review experience should invite consideration of:

1. **Composition and layout** — balance, framing, spacing, scale, and hierarchy.
2. **Visual coherence** — palette, typography, materials, lighting, and a
   consistent design language.
3. **Spatial legibility** — whether roads, movements, conflicts, queues, ramps,
   and network structure can be understood.
4. **Information design** — whether controls and live information clarify the
   system without overwhelming it.
5. **Motion fidelity** — whether acceleration, braking, turning, merging,
   walking, transitions, and feedback look intentional and plausible.
6. **Atmosphere and polish** — detail, finish, responsiveness, and the sense
   that the artifact is a complete experience.
7. **Originality and delight** — memorable choices or moments that exceed a
   generic functional implementation.
8. **Integration with the mission** — whether visual design makes the traffic
   simulation more comprehensible and compelling rather than distracting from
   it.

This visual interpretation remains separate from validity, acceptance,
sustainable throughput, and agent resource efficiency. The eventual site may
support pairwise human comparison or a calibrated qualitative judge, but P0's
responsibility is to preserve and present the evidence exceptionally well.

## Public versus private material

### Public challenge pack

- Narrative prompt.
- Infrastructure constraints, dimensions and tolerances, time convention,
  right-of-way rules, and traffic-validity rubric.
- The complete four-method `gates/v1` contract and semantic gate diagram.
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

### Fair-shot boundary

Private judging may test generalization and performance; it must not hide a
correctness contract. Before surrendering an attempt, a capable model should
be able to detect basic contract misunderstandings and debug its artifact in a
representative real-browser run.

The public pack should therefore provide:

- The complete versioned arrival and finish shapes, with small valid examples.
- A deterministic smoke scenario that exercises every gate and traveler type
  without revealing the scored load schedule.
- A runnable conformance tool that checks registration, completion identity and
  exit reconciliation, offline readiness, and browser/runtime errors.
- Access to useful console/log evidence in a documented, bounded format.
- Stable assertion identifiers and failure details describing the observed
  contract violation.

The public tool is a contract debugger, not a score oracle. Passing it does not
reveal or guarantee scored capacity, expose private cases, or substitute for
robust design. The model does not receive an interactive query channel into the
private judge.

The private judge may vary seeds, mixes, timings, demand intensity, failure
windows, and capacity search. It must not require an undocumented field,
lifecycle rule, semantic gate, or tool behavior. Hidden values
should decide robustness and score, not whether the model could have known how
to be correct.

Diagnostics should say what was observed and which public contract was
violated, but should not prescribe an algorithm, data model, class structure,
traffic-control policy, rendering technology, layout, or visual style. Public
examples are conformance examples, not reference implementations. The same
tool access, feedback categories, attempt count, and model-work budget apply to
every comparable SUT.

## Threshold calibration

Physical bounds and correctness rules are public. Hidden schedules may vary
demand but must not alter car size, road geometry bounds, speed limits, signal
rules, or acceptance requirements. Stage durations, demand rates, delay
limits, failure windows, and passing capacity thresholds must be calibrated
against the public envelope using:

1. Deterministic fixture artifacts.
2. At least one evaluator-owned viable implementation kept outside the public
   repository.
3. Pilot runs from several model/harness classes.
4. Visual inspection to reject technically passing but physically implausible
   behavior.

Any scoring-threshold change creates a new judge-pack version. A physical or
acceptance-contract change creates a new challenge revision as well. Neither
silently rewrites historical results. Fixture-only tests must remain runnable
without model accounts, an inference server, or private reference material.
