# 0014 — Seam-first evaluation and an active harness target

**Status:** Accepted
**Date:** 2026-08-30

## Context

The first implementation established a strong contract, execution, isolation,
gates, and bundle foundation around Busy Intersection. The next risk is not
missing feature breadth; it is allowing the conductor and evaluator seams to
remain coupled to Codex and the intersection while adding more product surface.

The benchmark also needs a clear value model. A simulation must first be a
working participant in evaluator-owned demand. Only then should sustainable
throughput, efficiency, and visual quality differentiate eligible results.

## Decisions

### Busy Intersection remains primary

Busy Intersection is the active benchmark and the main implementation focus.
Future city simulations remain open extensions rather than requirements for the
current milestone.

The former “5x5 Rush descriptor/topology fixture” is renamed the **Challenge
Portability Fixture**. Its purpose is to prove that a second challenge can pass
through the challenge, browser, bundle, and reporting boundaries without
Busy-specific branches in the conductor. It is not a partial city simulation.

The fixture must not force future challenges to use intersection-specific
semantics. A future city may introduce its own versioned challenge protocol or
evaluation objects through the challenge adapter while reusing the generic run,
artifact, capture, evidence, and reporting lifecycle.

### Eligibility precedes performance

Evaluation has an explicit functional floor. A candidate must use the public
interface correctly, produce valid evaluator-observed work, and remain
structurally and operationally valid before receiving performance comparisons.

Eligible candidates receive an independent performance vector including
throughput, qualifying offered load, latency, backlog, and recovery. Relative
comparisons are derived from immutable absolute measurements at report time.
P0 does not introduce a single composite score, and performance cannot rescue
an invalid, unsafe, unverifiable, or dishonest artifact.

The public checker is an interface debugger. Private demand and scoring measure
whether the simulation generalizes beyond the known smoke case and handles
increasing load. Public conformance and private performance therefore serve
different purposes.

### Current versions are resolved at run time

The default harness policy is to use the most recent available harness release.
Harness adapters expose bounded update discovery and, where supported, update
the harness before a run. Updates never occur during a run. The exact version,
executable identity, update result, and adapter version used by the run remain
part of provenance so a moving target is still explainable.

### Pi-wiggum is the next proving path

After the seams are complete, the first additional real SUT is Pi-wiggum with a
local model. Pi, its Wiggum workflow/configuration, the local model provider,
and the model identity remain separate resolved components. This path proves
the adapter and lifecycle contracts; it must not add a Pi-specific conductor
branch. The concrete local serving runtime is an environment decision recorded
by the provider adapter.

### Pre-evaluation failures do not produce result bundles

A `.ralph.zip` result bundle is produced only after a candidate has been
preserved and private evaluation has begun. A total agent/preflight failure
with no candidate, or an evaluator that cannot start, fails fast with concise
operator-visible evidence and does not create a diagnostic result bundle.
Candidate-level evaluation failures remain valid result outcomes because they
have an artifact and evaluation evidence to report.

### Seam completion precedes reporting breadth

The next milestone completes and tests the challenge, harness, lifecycle,
evaluation, and failure boundaries. Static reporting, broader city work, and
additional product polish follow that milestone rather than driving it.

## Consequences

- The original Codex path remains useful as a current-version compatibility
  path, but its exact historical version is not a permanent acceptance gate.
- Pi-wiggum/local execution is an intentional scope amendment, not permission
  to add arbitrary integrations before the common seams are proven.
- Bundles remain clean analytical units: they represent evaluated artifacts,
  not every failed attempt to start the system.
- The report can show “working” as an eligibility result and “better” as a
  performance comparison without hiding failures inside a weighted number.
- The Challenge Portability Fixture protects future city freedom while keeping
  the present implementation focused on the intersection.
