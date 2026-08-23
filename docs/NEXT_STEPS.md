# Prioritized next steps

This is the resume point after the first end-to-end P0-A live run on
2026-08-23. The run produced a valid immutable bundle and a visually strong
Busy Intersection, but the candidate did not pass the contract or produce
valid throughput. That is useful benchmark separation, not an infrastructure
failure.

## Decisions already made

Do not reopen these without new evidence:

- P0 live SUT: Codex CLI + ChatGPT subscription + GPT-5.6 Luna.
- P0 challenge: Busy Intersection; the 5x5 Rush city is P0-B.
- P0 protection: portable L0/unsealed staging. Strong isolation-tool selection
  is deferred by [ADR 0012](adr/0012-defer-strong-isolation-backends.md).
- Subscription cost remains unavailable rather than zero. OpenRouter is the
  next metered/reference-cost implementation; quota allocation is later.
- Interactive `c` checks inspect only local structural evidence and never make
  an inference call or print model prose.
- Human preview uses the evaluator-recorded WebM, not live execution of
  candidate HTML.
- Operator experiment TOMLs and generated `results/` remain local and ignored
  by Git.

## Evidence from live run 1

- One independent run used both allowed model attempts and produced a valid
  40-entry `.ralph.zip` bundle.
- The artifact was visually impressive, confirming that the challenge has the
  intended subjective payoff.
- The static offline check falsely interpreted the CSS custom property
  `--ws:64px` as a `ws:` WebSocket URL.
- Runtime judging rejected a malformed movement identity
  (`movement.id must be a non-empty string`) and measured zero valid
  throughput.
- The repair attempt received static public-check feedback but did not receive
  the later browser/runtime contract failure, so it had no opportunity to fix
  the movement bridge.
- Some failed assertions use success-oriented detail text such as “browser
  snapshot has no runtime errors,” making failure evidence harder to read.
- The public pack names the `traffic/v1` methods but does not yet ship complete
  payload schemas, valid lifecycle examples, dynamics limits, or an
  agent-runnable browser checker.
- Conversely, the current public scenario pack exposes the same pilot stage
  schedule used by the live evaluator. Public conformance inputs and private
  scored profiles are not yet meaningfully separated.

## Fair-shot design guardrails

The benchmark should be difficult because the system must design, implement,
debug, and optimize a rich simulation—not because success depends on guessing
an undocumented interface.

- Publish every correctness requirement and the complete `traffic/v1` schema.
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

### 1. Complete the fair-shot public contract and checker

**Priority:** blocking

**Estimate:** 1–2 engineering days

- Publish complete versioned request/response/event schemas, small valid
  lifecycle examples, and every required physical/dynamics bound.
- Add a deterministic, deliberately modest scenario covering every movement
  and lifecycle shape plus an agent-runnable real-browser conformance command.
- Separate that representative public scenario from private scored profiles;
  passing the public command must prove contract readiness, not reveal
  throughput capacity or guarantee benchmark acceptance.
- Replace the broad URL regex with context-aware offline dependency checks that
  do not confuse CSS custom properties, JavaScript comments, or harmless
  namespace strings with network access.
- Add the first live artifact pattern (`--ws:64px`) as a regression fixture.
- Make every failed assertion's detail describe the observed failure rather
  than reuse success-oriented text.
- Aggregate repeated stage/movement failures for operator-facing summaries
  while preserving full assertion evidence in the bundle.

**Exit:** a model can implement and debug `traffic/v1` without guessing any
field or lifecycle convention; the live artifact's static check fails only for
a real external dependency; public tooling does not expose the scored load
profile or prescribe an implementation.

### 2. Give the model a fair, non-prescriptive acceptance loop

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
`traffic/v1` can repair and pass on attempt two; neither the tool nor feedback
dictates its algorithm or visual design; both attempts remain auditable.

### 3. Extract a real challenge execution boundary

**Priority:** blocking skeleton work

**Estimate:** 2–3 engineering days

- Define a versioned challenge adapter/descriptor owning public-pack
  materialization, scenario construction, expected topology, evaluation,
  capture instructions, and challenge-specific bundle identity.
- Move Busy Intersection imports and path knowledge out of the generic
  conductor and browser-worker orchestration.
- Add a descriptor/topology-only 5x5 Rush fixture that traverses this boundary;
  do not implement the city simulation or production judge yet.

**Exit:** the generic conductor contains no Busy Intersection branch, and the
intersection plus skeletal city fixture traverse the same challenge contract.

### 4. Complete harness polymorphism through execution

**Priority:** high skeleton work

**Estimate:** 1–2 engineering days

- Let the selected harness adapter provide/factory the `AttemptExecutor` and
  lifecycle evidence instead of constructing `CodexAttemptExecutor` in the
  conductor.
- Exercise the complete conductor with two fake harness implementations, not
  only resolver composition tests.
- Keep P0's sole live implementation Codex; this is contract completion, not a
  second-harness integration.

**Exit:** adding a compatible fake harness requires registry work but no
conductor branch or Codex import.

### 5. Make terminal completion status unmistakable

**Priority:** high

**Estimate:** 0.5–1 engineering day

- Distinguish “bundle produced and validated” from “candidate passed the
  benchmark” in the final console summary.
- Print the selected attempt, static acceptance, runtime outcome, peak valid
  throughput, repair usage, and bundle path in a compact block.
- Keep the default-yes recorded-overview prompt after that summary.

**Exit:** an operator can answer “did it work?” without opening JSON or asking
for bundle inspection.

### 6. Implement `rb build` and the first static report

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

### 7. Reconcile reproducibility claims with the implementation

**Priority:** high before canonical publication

**Estimate:** 0.5–1 engineering day

- Keep the configuration lifecycle documented as a target contract while P0
  implements only read-only subscription detection, scoped materialization,
  and planned temporary-root cleanup—not generalized transactional rollback.
- Pin the supported Python Playwright package exactly, record the installed
  Chromium executable digest, and downgrade mismatches to experimental.
- Add a lightweight release checklist/test for executable claims in the README
  and P0 plan so architectural prose cannot silently outrun the code.

**Exit:** documentation and bundle provenance distinguish implemented,
verified, and future behavior without relying on implication.

### 8. Portability pass for macOS and Windows

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
  P0 is explicitly portable L0/unsealed. A first live run has also occurred,
  though it did not reach valid throughput and therefore did not calibrate the
  sustainable-load curve.
- **Deferred deliberately:** the legacy corpus needs an explicit fate, but it
  should not distort the immutable vNext bundle model or block the first static
  product surface.
