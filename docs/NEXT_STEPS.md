# Prioritized next steps

The next milestone is shared execution/configuration consolidation described
below. The operator
has observed generated artifacts that collide, ignore signals, leave their
lanes, or use implausible vehicle/road scale. Some local-model artifacts do
not establish a working simulation at all. Successful gate callbacks and
attractive animation therefore cannot establish traffic validity.

The implementation status and historical evidence below describe the existing
P0-A path; they do not establish that these new acceptance requirements have
been implemented or verified.

## Clearer goals

The [traffic contract](TRAFFIC_CHALLENGES.md) is authoritative for what a
simulation must do: finite travelers move through a shared world, avoid
collisions, obey signals, follow lanes, use realistic physical scale, and
complete their requested trips. The document defines the public envelope,
right-of-way rules, clock convention, evidence, and counterexamples.

[ADR 0017](adr/0017-traffic-validity-before-performance.md) records the change
from optional physical interpretation to required traffic validity, while
retaining `gates/v1`. The executable challenge remains v1 until the v2 contract
can be delivered and evaluated honestly. Diagnostic callback throughput does
not establish a working simulation.

## Refactor phases

Proceed in this order and pause after each phase. Do not start live model
runs or introduce additional integrations as part of mechanical cleanup.

### 1. Establish the traffic contract — complete, 2026-09-05

- Define the traffic concepts, safety rules, public physical baseline, shared
  assignment, time convention, and evidence requirements in one contract.
- Amend the vision, acceptance interpretation, repository guidance, and ADRs.
- Reserve v2 for changed semantics; preserve the executable v1 pack and schemas.

**Exit:** Documentation distinguishes implemented behavior from the v2 target;
all required rules have a public definition and planned evidence/counterexample.
Physical baseline values still require fixture calibration. No runtime change
or claim that traffic validity is already enforced.

### Live calibration evidence — 2026-09-06

The first post-merge Codex/Luna run produced a valid diagnostic bundle at
`fa18b063-dff1-4f91-8ef5-1ee1dd95d10a`. Its private v1 load simulation serviced
80/80 cars and 16/16 pedestrians, measured 81 vehicles/minute, and recovered
its backlog, but the original public smoke horizon ended before the second
pedestrian finished (5/6 travelers). The public pack now grants a modest,
unscored 12-second settle window after the last arrival and reports missing
public traveler IDs in bounded repair feedback. Replaying the preserved
artifact under that calibrated public pack completed all 6/6 travelers with no
runtime or network errors. This calibrates the v1 interface smoke boundary; it
does not establish the v2 physical-validity requirements below.

### 2. Remove unused machinery and duplicate calculations — complete, 2026-09-06

- Remove the unused run-state machine and cleanup stack/report, retaining
  coverage of the actual conductor lifecycle and rollback paths.
- Remove the unused host-environment helper and redundant repair wrapper;
  retarget any useful wrapper tests to the production boundary.
- Remove the unread challenge scenario document and its serialization.
- Reuse the existing safe artifact-tree hash; use Python's file digest helper
  where equivalent. Build the smoke scenario directly with validated domain
  objects instead of serializing and reparsing an intermediate dictionary.

**Exit:** Existing account-free tests pass; runtime behavior, bundle schemas,
path/secret protections, and cleanup guarantees remain unchanged.

Phase 2 removed the unused run-state machine, generic cleanup stack/report,
host-environment helper, and compatibility repair wrapper. It also removed the
unread scenario-document field, built the public smoke scenario directly from
validated gate objects, reused the safe artifact-tree hash, and used
`hashlib.file_digest` for the browser executable digest. The full account-free
suite passes (138 tests); no live model run was started for this mechanical
cleanup.

### 3. Consolidate shared execution and configuration

- Share conformance execution while callers retain ownership of temporary or
  preserved output directories.
- Share attempt bookkeeping across Codex and Pi; keep native invocation,
  parsing, configuration, and raw evidence at adapter boundaries.
- Use one capability declaration for wizard, resolver, and invocation options;
  remove unused option declarations and keep known models declarative and
  unknown models conservative. Retain the three typed adapter families.
- Give every client the complete challenge. Remove the Pi-only animation
  replacement; label any reduced tool-call calibration separately.

**Exit:** Both client paths receive the same assignment and preserve attempt,
resource, feedback, and cleanup evidence. Shared validation has one source.

### 4. Make acceptance and reporting truthful

- Represent protocol conformance, traffic review, load performance, and visual
  quality separately, following the [measurement model](MEASUREMENT_MODEL.md).
- Support explicit traffic-review states and evidence references. Keep later
  reviews outside immutable bundles, tied to run ID and artifact hash.
- Exclude failed, pending, and unverifiable traffic from performance comparison;
  retain diagnostics. Preserve the L0 experimental/official-ranking boundary.
- Version changed result/capture semantics, describe elapsed evaluation time
  accurately, and retain historical readers without inventing physical passes.

**Exit:** Acceptance and report tests exercise missing/failed/insufficient
review, provenance mismatches, immutable input, and historical compatibility.
The staged v2 path cannot be presented as calibrated production performance.

### 5. Validate physical behavior and calibrate load

- Identify the existing passing artifact as a protocol fixture. Exercise a
  physically credible evaluator-owned reference under the public envelope.
- Add observation cases for car/car and car/pedestrian collisions, red-light
  entry, lane departure, scale abuse, false finishes, starvation, backlog, and
  recovery. Test the claimed observation method, not preset verdict fields.
- Validate human-review coverage and any proposed detector against those
  cases. Preserve explicit uncertainty where the evidence cannot decide.
- Calibrate demand and recovery against safe behavior; version the private
  judge. Materialize the v2 public pack and shared scenario profile, verify
  end-to-end evidence, then activate v2 only when all release conditions hold.

**Exit:** Each validity rule has demonstrated observation coverage and a
counterexample. Account-free fixture tests do not need private material;
private reference/pilot evidence supports the production thresholds. Safety
remains mandatory under overload, and v1/v2 results are not mixed.

### 6. Consolidate documentation around the working solution

- Keep README focused on usage, P0_PLAN on current scope and completion, and
  this file on outstanding work. Link to one owner for each domain contract.
- Remove duplicated requirements and obsolete implementation instructions.
  Condense local-model handoff history while retaining experiment/run IDs and
  the evidence needed to interpret failures.
- Preserve historical ADRs and clearly mark their amendments; remove claims
  for functionality that is neither implemented nor in the current milestone.

**Exit:** Commands and examples match the implemented system, each requirement
has one authoritative home, and historical evidence remains interpretable.

## Decisions already made

Retain these existing P0 choices except where the refactor requirements above
explicitly revise traffic acceptance or the shared challenge:

- Busy Intersection is the primary challenge. The future city remains open for
  extension; its P0 seam proof is the Challenge Portability Fixture, not a
  partial 5x5 implementation.
- The initial live SUT is Codex CLI + ChatGPT subscription + GPT-5.6 Luna.
  Codex is refreshed to the most recent available release before a run and
  records the exact version and executable identity.
- Pi with the installed Pi-wiggum extension and a local model served by LM
  Studio is the next real SUT used to prove the local harness/provider path.
  Controlled proving runs use Pi's normal tool loop so Ralph can apply one
  evaluator-controlled repair; the native Wiggum TPM prompt remains available
  as a distinct `loop = "native"` mode.
- P0 protection: portable L0/unsealed staging. Strong isolation-tool selection
  is deferred by [ADR 0012](adr/0012-defer-strong-isolation-backends.md).
- Eligibility comes before performance comparison: a candidate must produce a
  working, valid simulation before throughput, capacity, latency, backlog, or
  recovery differentiate it from other eligible results. P0 has no composite
  score.
- Subscription cost remains unavailable rather than zero. OpenRouter is the
  next metered/reference-cost implementation; quota allocation is later.
- Interactive `c` checks inspect only local structural evidence and never make
  an inference call or print model prose.
- Human preview uses the evaluator-recorded WebM, not live execution of
  candidate HTML.
- Operator experiment TOMLs and generated `results/` remain local and ignored
  by Git.
- A complete pre-evaluation failure with no candidate or no started evaluator
  fails fast without a result bundle. A preserved candidate that reaches
  evaluation still receives a bundle when evaluation fails.
- Seam completion still comes before broader city work or additional product
  polish. A minimal static report now exists so failed and passing evidence is
  inspectable while the remaining acceptance seams are completed.
- Current-toolchain refresh and local-provider readiness happen before model
  evaluation, never during an active run. Discovery and `rb doctor` remain
  read-only.

## Evidence from live run 1

- One independent run used both allowed model attempts and produced a valid
  40-entry `.ralph.zip` bundle.
- The artifact was visually impressive, confirming that the challenge has the
  intended subjective payoff.
- The static offline check falsely interpreted the CSS custom property
  `--ws:64px` as a `ws:` WebSocket URL.
- The retired `traffic/v1` runtime judge rejected a malformed movement identity
  (`movement.id must be a non-empty string`) and measured zero valid
  throughput.
- The repair attempt received static public-check feedback but did not receive
  the later browser/runtime contract failure, so it had no opportunity to fix
  the movement bridge.
- That failure helped expose that the rich topology/snapshot/event contract was
  testing interface plumbing more than simulation design. It has been replaced
  by the four-method `gates/v1` arrival/finish interface.
- The public pack now contains only an unscored smoke schedule and semantic gate
  diagram. Production arrival mixes, stage rates, seeds, and thresholds remain
  evaluator-owned.

## Evidence from the `gates/v1` replacement

- The checked-in passing artifact completed a real 50-second monitored
  Chromium run: 60/60 cars and 13/13 pedestrians finished with no invalid
  notifications.
- The worker collected 198 live ledger samples while recording the same run,
  then derived monitored throughput, completion latency, stage backlog, and
  cooldown recovery.
- Missing callbacks are reported as `unmeasurable`, not as zero throughput.
- Context-aware offline checks accept CSS custom properties such as
  `--ws:64px` while still rejecting real external URLs.
- The complete unit and contract suite contains 138 passing tests at this
  checkpoint; the command below is authoritative as the suite grows.

## Fair-shot design guardrails

The benchmark should be difficult because the system must design, implement,
debug, and optimize a rich simulation—not because success depends on guessing
an undocumented interface.

- Publish every rule of the complete four-method `gates/v1` contract.
- Give the model a deterministic public smoke scenario and a runnable
  conformance tool that exercises all required lifecycle shapes.
- Provide browser console/runtime evidence and stable assertion IDs in a
  bounded logging format.
- Keep hidden seeds, demand mixes, stress levels, failure windows, and scoring
  schedules private so the final judge measures generalization and capacity.
- Never let a private test introduce a new required field, lifecycle rule, or
  coordinate convention absent from the public contract.
- Report observed violations and relevant evidence, not a suggested algorithm
  or code patch.
- Preserve latitude over simulation architecture, signal policy, data model,
  rendering technology, 2D/2.5D/3D choice, layout, and visual style.
- Give comparable SUTs the same tools, feedback classes, repair count, and
  model-work budget.
- Treat the public checker as a contract debugger, not a score oracle: it must
  not reveal private cases, load schedules, capacity thresholds, or reference
  implementation choices.

## P0-A — next session

### 0. Establish current-toolchain and local-provider preflight — implemented

**Priority:** completed prerequisite; local Pi proving run calibrated

- Delivered a generic harness/provider lifecycle for current-toolchain refresh
  before the first model invocation. Codex uses `codex update`; Pi uses
  `pi update` followed by `pi update --extensions`.
- Delivered the LM Studio provider boundary around `lms runtime update --all
  --yes`, `lms server status --json`, `lms server start`, `lms load`, and
  `lms ps --json` verification.
- Added a provider-owned, idempotent rollback handle. It restores only the
  server/model state introduced for the run, including after a failed load.
- Recorded before/after versions, executable identities, Pi extension/package
  identities, runtime/server/model state, update results, and unsupported
  freshness claims as redacted provenance.
- Added stale, current, unavailable, timeout, and update-failure fixtures
  without making a generation request. A failed preflight stops before model
  invocation and does not produce a result bundle.

**Delivered:** the selected harness and local inference runtime are refreshed or
explicitly proven current before evaluation; the selected model is prepared and
verified on the serving provider; provider state is restored after the run; all
toolchain evidence is attributable and no update can occur during an active run.

### 0.1. Local Gemma proving result — calibrated, not yet passing

- `gemma-4-12b-it-mlx` was exercised through Pi 0.84.4 with the installed
  `pi-wiggum` and `pi-subagents` extension graph, after the required refresh
  preflight.
- The direct Pi tool path can create a candidate. The bounded conductor now
  stops Pi when a new candidate entrypoint is written, so post-write model
  narration does not consume the evaluation budget.
- A candidate reached browser evaluation and received semantic repair feedback.
  The model did not complete the repair within the bounded local model budget,
  so this is an honest below-bar proving result rather than a passing score.
- Continue model/tool-call calibration or select a stronger local model; do not
  weaken the evaluator or fabricate a result bundle.

### 1. Correct the functional eligibility boundary — implemented

**Priority:** completed blocking seam

- Capacity-stage and recovery failures now enter the final evaluation outcome.
- The evaluator exposes `performance_eligible` separately, so a working but
  overloaded artifact remains measurable while a non-working artifact cannot
  enter performance comparison.
- Fixtures cover both the overloaded-working and missing-interface paths.
- Keep functional eligibility separate from the performance vector; never let
  high throughput compensate for invalid or dishonest behavior.

**Exit:** met. The evaluator cannot report `passed` when a qualifying held stage
or recovery requirement fails, and tests make the working-before-performance
rule explicit.

### 2. Ship the agent-runnable public gate check — implemented

**Priority:** completed blocking seam

**Estimate:** 0.5–1 engineering day

- Added `rb conformance <candidate>` with `--json` output for the small public
  smoke schedule and concise registration/finish diagnostics without exposing
  the production load.
- The evaluator is unit-tested against passing and deliberately broken
  implementations; a real browser run remains operator/environment-dependent.
- Keep it a contract debugger: report observed callback/identity/exit/runtime
  failures without suggesting a simulation architecture or traffic algorithm.

**Exit:** met for the public command. A model can validate the two arrival
callbacks and two finish methods without guessing; the scored profile remains
private; passing the command proves interface readiness but does not predict
benchmark capacity.

### 3. Give the model a fair, non-prescriptive acceptance loop — implemented

**Priority:** remaining blocking integration

**Estimate:** 2–4 engineering days

- Integrate the public conformance command and representative smoke scenario
  into the staged challenge adapter and attempt lifecycle.
- Each static candidate that reaches browser evaluation is checked against the
  public smoke contract and the private profile. The public result is preserved
  as raw attempt evidence and its stable failures are included in bounded
  repair feedback.
- Give the model bounded browser-console and structured-log inspection so it
  can debug the same artifact state the evaluator will inspect.
- Evaluate the initial candidate through browser/runtime contract checks before
  deciding whether to spend the one repair attempt.
- Return stable assertion IDs, observed values, and public contract violations
  to the repair prompt without exposing private scenario values, hidden stress
  schedules, or implementation advice.
- Preserve attempt-specific static and runtime evidence so the final bundle
  explains what changed.
- Avoid recording infrastructure judging as a model invocation or charging it
  against model-work time.
- Decide whether the overview is captured for every attempt or only the final
  selected artifact; keep the decision explicit in bundle provenance.

**Exit:** met for the P0 acceptance path. Two deliberately different
implementations can use the same public command to reach or fail conformance;
the controlled loop preserves the public result, evaluates the private profile,
and feeds combined public/private contract failures into attempt two without
leaking private load values. Richer structured-log presentation remains a
future polish item.

### 4. Extract a real challenge execution boundary — implemented skeleton

**Priority:** completed skeleton work

**Estimate:** 2–3 engineering days

- Added a versioned challenge adapter boundary owning public-pack
  materialization, scenario construction, evaluation, capture selection,
  repair vocabulary, and challenge-specific prompt details.
- Busy Intersection paths are out of the generic conductor; a future-city
  protocol/topology fixture exercises the registry and run boundary in tests.
- The full future-city evaluator remains deferred; the fixture is an
  architectural proof, not a partial city simulation.

**Exit:** met for the P0 skeleton. The generic conductor contains no
Busy Intersection public-pack/scenario branch, and the portability fixture
traverses the generic run boundary without imposing intersection semantics.

### 5. Complete harness polymorphism through execution — implemented

**Priority:** completed skeleton work

**Estimate:** 1–2 engineering days

- The selected harness adapter now provides/factories the `AttemptExecutor`; the
  conductor no longer constructs `CodexAttemptExecutor` or rejects Pi by name.
- The complete conductor is exercised through Codex and Pi/local compositions
  with fixture executors.
- Keep this deliberately narrow harness breadth; broader integrations remain
  out of scope.

**Exit:** adding a compatible fake harness requires registry work but no
conductor branch or Codex import.

### 6. Make terminal completion status unmistakable — implemented

**Priority:** completed high-priority seam

**Estimate:** 0.5–1 engineering day

- The final console summary distinguishes validated bundle production from a
  full benchmark pass.
- It prints selected attempt, public acceptance, simulation outcome,
  measurement status, peak monitored throughput, repair usage, and bundle path.
- Keep the default-yes recorded-overview prompt after that summary.

**Exit:** met. An operator can answer “did it work?” without opening JSON or
asking for bundle inspection.

### 7. Add the Pi-wiggum/local native harness path — controlled proving complete

**Priority:** next proving action

- Pi with the Pi-wiggum extension is now a native harness/workflow path, with a
  local model provider and conservative model binding, without a conductor
  branch.
- Pi JSONL usage, turn, tool, raw-stream, and scoped-provider configuration
  evidence are normalized behind the harness adapter.
- Capture Pi's executable/version and Wiggum extension/dependency identities
  from the preflight toolchain record.
- Keep the native Wiggum loop distinct from Ralph's evaluator-controlled loop;
  count its internal iterations against the shared model-work budget.
- Two controlled Pi/Wiggum local evaluations have now run after selecting and
  verifying Gemma and GPT-OSS models. Neither cleared the working-solution bar;
  both results remain useful calibration evidence. A native TPM-loop run is
  still optional and deferred with the current hardware.

**Exit:** met for controlled proving. The same conductor and challenge path
can run the Codex and Pi-wiggum/local compositions, while each result clearly
identifies the exact harness, workflow, provider, and model used.

### 8. Implement `rb build` and the first static report — implemented

**Priority:** completed high-priority seam

**Estimate:** 3–5 engineering days

- `rb build` reads and validates bundles without mutating source evidence.
- The report separates local/cloud context and shows model/harness/provider,
  configuration/provenance, time, attempts, tokens, cost availability,
  throughput, failure assertions, L0 status, poster, and animated overview.
- Failure and non-passing results remain first-class; invalid bundles are
  quarantined outside normal views.

**Exit:** met. `rb build --source results/inbox --output site` produces a
static, portable site containing the preserved live bundles and recorded
animations.

### 9. Reconcile reproducibility claims with the implementation — partially implemented

**Priority:** high before canonical publication

**Estimate:** 0.5–1 engineering day

- Keep the configuration lifecycle documented as a target contract while P0
  implements only read-only detection, scoped materialization, and planned
  temporary-root cleanup—not generalized transactional rollback.
- The supported Python Playwright package is pinned exactly, and browser
  capture now records the Chromium executable digest. Downgrading mismatches
  to experimental and the release checklist remain.
- Add a lightweight release checklist/test for executable claims in the README
  and P0 plan so architectural prose cannot silently outrun the code.

**Exit:** documentation and bundle provenance distinguish implemented,
verified, and future behavior without relying on implication.

### 10. Portability pass for macOS and Windows

**Priority:** high after the Linux vertical slice stabilizes

**Estimate:** 2–4 engineering days

- Chromium/FFmpeg discovery now prefers Playwright's standalone headless shell
  on macOS/Linux and honors explicit overrides; temporary-directory handling
  still needs broader validation.
- Verify process-group cancellation and single-key progress input on each OS.
- Exercise Codex authentication and native `workspace-write` semantics without
  upgrading the L0 claim.
- Add CI/fixture coverage where hardware execution is unavailable.

**Exit:** `rb doctor`, one no-model rehearsal, and one live run complete on
Linux, macOS, and Windows/WSL with platform provenance recorded.

## After P0-A

1. Add OpenRouter as the first metered provider and canonical reference-price
   source.
2. Use the growing corpus to refine failure modes, judge calibration, and
   capacity-search schedules.
3. Add multiple independent runs and statistical comparison views.
4. Implement the 5x5 Rush city/freeway challenge through the same contracts.
5. Evaluate and select strong L1/L2 isolation backends cross-platform.
6. Add Google Drive bundle storage/ingest after the local immutable
   bundle/report path is stable.
7. Give the legacy `llm-eval` corpus an explicit archival/read-only-view policy
   rather than silently treating it as migrated data.

## Independent review triage

An independent 2026-08-23 comparison with `llm-eval` was checked against the
current implementation. Its useful findings are reflected above:

- **Confirmed and promoted:** challenge execution was hard-coded; harness
  polymorphism stopped before execution; the public checker/contract pack was
  incomplete; `rb build` was absent; configuration and browser-stack docs
  overstate current implementation; a passing live artifact is still needed
  to calibrate capacity separation. The challenge adapter, public conformance
  command, acceptance-loop integration, and first static report now address
  the corresponding seam gaps.
- **Intentional but monitored:** one live SUT and unavailable subscription cost
  are deliberate P0 scope reductions, provided the execution contracts and
  cost provenance remain honest.
- **Already superseded:** Bubblewrap is no longer a P0 dependency or L1 claim;
  P0 is explicitly portable L0/unsealed. The rich `traffic/v1` bridge is also
  retired; a real `gates/v1` fixture run now proves the minimal monitored
  boundary, though a fresh model-generated artifact is still needed for
  capacity calibration.
- **Deferred deliberately:** the legacy corpus needs an explicit fate, but it
  should not distort the immutable vNext bundle model or block the first static
  product surface.
