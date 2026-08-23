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

### 1. Correct judge diagnostics and offline detection

**Priority:** blocking

**Estimate:** 0.5–1 engineering day

- Replace the broad URL regex with context-aware offline dependency checks that
  do not confuse CSS custom properties, JavaScript comments, or harmless
  namespace strings with network access.
- Add the first live artifact pattern (`--ws:64px`) as a regression fixture.
- Make every failed assertion's detail describe the observed failure rather
  than reuse success-oriented text.
- Aggregate repeated stage/movement failures for operator-facing summaries
  while preserving full assertion evidence in the bundle.

**Exit:** the live artifact's static check fails only for a real external
runtime dependency, and every emitted failure message is actionable and
semantically consistent with `result=fail`.

### 2. Give the model a fair, non-prescriptive acceptance loop

**Priority:** blocking

**Estimate:** 2–4 engineering days

- Ship a public conformance command and representative smoke scenario in the
  staged tool/challenge pack. The model can invoke it while building; it checks
  the public contract but does not contain a reference implementation or act
  as a capacity/score oracle.
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

### 3. Make terminal completion status unmistakable

**Priority:** high

**Estimate:** 0.5–1 engineering day

- Distinguish “bundle produced and validated” from “candidate passed the
  benchmark” in the final console summary.
- Print the selected attempt, static acceptance, runtime outcome, peak valid
  throughput, repair usage, and bundle path in a compact block.
- Keep the default-yes recorded-overview prompt after that summary.

**Exit:** an operator can answer “did it work?” without opening JSON or asking
for bundle inspection.

### 4. Implement `rb build` and the first static report

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

### 5. Portability pass for macOS and Windows

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
