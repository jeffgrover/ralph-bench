# Prioritized next steps

This is the resume point after replacing the original rich traffic protocol
with the minimal `gates/v1` arrival/finish boundary and accepting the
seam-first direction. The first P0-A model run on 2026-08-23 remains valuable
evidence: it produced a valid immutable bundle and a visually strong Busy
Intersection, but exposed that interface plumbing was dominating measurement.

## Decisions already made

Do not reopen these without new evidence:

- Busy Intersection is the primary challenge. The future city remains open for
  extension; its P0 seam proof is the Challenge Portability Fixture, not a
  partial 5x5 implementation.
- The initial live SUT is Codex CLI + ChatGPT subscription + GPT-5.6 Luna.
  Codex is refreshed to the most recent available release before a run and
  records the exact version and executable identity.
- After the common seams are complete, Pi with the native Pi-wiggum extension
  and a local model served by LM Studio is the next real SUT used to prove the
  local harness/provider path.
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
- Seam completion comes before static reporting breadth, broader city work, or
  additional product polish.
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
- The complete unit and contract suite contains 108 passing tests.

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

**Priority:** completed prerequisite; first real Pi-wiggum run is next

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

### 1. Correct the functional eligibility boundary

**Priority:** blocking

- Include capacity-stage failures and recovery failures in the final evaluation
  outcome rather than considering only immediate assertions.
- Add fixtures proving that a working-but-overloaded artifact is failed for
  performance while a non-working artifact is ineligible or unmeasurable.
- Keep functional eligibility separate from the performance vector; never let
  high throughput compensate for invalid or dishonest behavior.

**Exit:** the evaluator cannot report `passed` when a qualifying held stage or
recovery requirement fails, and tests make the working-before-performance rule
explicit.

### 2. Ship the agent-runnable public gate check

**Priority:** blocking

**Estimate:** 0.5–1 engineering day

- Add an agent-runnable command for the small public smoke schedule and concise
  registration/finish diagnostics without exposing the production load.
- Exercise that command against both checked-in fixtures and at least two
  deliberately different implementations.
- Keep it a contract debugger: report observed callback/identity/exit/runtime
  failures without suggesting a simulation architecture or traffic algorithm.

**Exit:** a model can validate the two arrival callbacks and two finish methods
without guessing; the scored profile remains private; passing the command
proves interface readiness but does not predict benchmark capacity.

### 3. Give the model a fair, non-prescriptive acceptance loop

**Priority:** blocking

**Estimate:** 2–4 engineering days

- Integrate the public conformance command and representative smoke scenario
  from step 1 into the staged tool/challenge pack and attempt lifecycle.
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

**Exit:** two deliberately different implementations can use the same public
tooling to reach conformance; a fixture that passes static checks but fails
`gates/v1` can repair and pass on attempt two; neither the tool nor feedback
dictates its algorithm or visual design; both attempts remain auditable.

### 4. Extract a real challenge execution boundary

**Priority:** blocking skeleton work

**Estimate:** 2–3 engineering days

- Define a versioned challenge adapter/descriptor owning public-pack
  materialization, scenario construction, expected topology, evaluation,
  capture instructions, and challenge-specific bundle identity.
- Move Busy Intersection imports and path knowledge out of the generic
  conductor and browser-worker orchestration.
- Add a Challenge Portability Fixture that traverses this boundary. It is an
  architectural proof, not a partial city simulation, and must not force a
  future city to use intersection-specific topology or protocol semantics.

**Exit:** the generic conductor contains no Busy Intersection branch, and the
intersection plus the Challenge Portability Fixture traverse the same generic
challenge lifecycle without limiting future city-specific protocols.

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

### 6. Make terminal completion status unmistakable

**Priority:** high

**Estimate:** 0.5–1 engineering day

- Distinguish “bundle produced and validated” from “candidate passed the
  benchmark” in the final console summary.
- Print the selected attempt, static acceptance, runtime outcome, peak
  monitored throughput, repair usage, and bundle path in a compact block.
- Keep the default-yes recorded-overview prompt after that summary.

**Exit:** an operator can answer “did it work?” without opening JSON or asking
for bundle inspection.

### 7. Add the Pi-wiggum/local native harness path — implementation ready; live run pending

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
- Run the first real local evaluation after selecting and verifying the model.

**Exit:** the same conductor and challenge path can run the Codex and
Pi-wiggum/local compositions, while each result clearly identifies the exact
harness, workflow, provider, and model used.

### 8. Implement `rb build` and the first static report

**Priority:** high

**Estimate:** 3–5 engineering days

- Read and validate bundles without mutating source evidence.
- Separate cloud/subscription and local tracks at the top level.
- Show model/harness/provider, hardware/configuration, time, attempts, tokens,
  cost availability, throughput/capacity, failure taxonomy, L0 badge, poster,
  and animated overview with a consistent visual system.
- Make failure and non-passing results first-class; the first live run should
  remain interesting and navigable rather than disappear from the report.

**Exit:** `rb build --source results/inbox --output site` produces a static,
portable site containing the first live bundle and its recorded animation.

### 9. Reconcile reproducibility claims with the implementation

**Priority:** high before canonical publication

**Estimate:** 0.5–1 engineering day

- Keep the configuration lifecycle documented as a target contract while P0
  implements only read-only detection, scoped materialization, and planned
  temporary-root cleanup—not generalized transactional rollback.
- Pin the supported Python Playwright package exactly, record the installed
  Chromium executable digest, and downgrade mismatches to experimental.
- Add a lightweight release checklist/test for executable claims in the README
  and P0 plan so architectural prose cannot silently outrun the code.

**Exit:** documentation and bundle provenance distinguish implemented,
verified, and future behavior without relying on implication.

### 10. Portability pass for macOS and Windows

**Priority:** high after the Linux vertical slice stabilizes

**Estimate:** 2–4 engineering days

- Generalize Chromium/FFmpeg discovery and temporary-directory handling.
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

- **Confirmed and promoted:** challenge execution is hard-coded; harness
  polymorphism stops before execution; the public checker/contract pack is
  incomplete; `rb build` remains absent; configuration and browser-stack docs
  overstate current implementation; a passing live artifact is still needed
  to calibrate capacity separation.
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
