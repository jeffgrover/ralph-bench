# ADR 0009: Build One Real Implementation Per Proven P0 Seam

**Status:** Accepted
**Date:** 2026-08-23

## Context

The legacy `llm-eval` repository already demonstrates the need for separate
harness, provider, and model behavior; normalized vendor events and metrics;
configuration ownership; immutable run identity; and report-time aggregation.
Those abstractions are evidence-backed extension seams, not guesses about a
hypothetical future.

Concrete legacy evidence includes the vendor runner registry and provider
conditionals in `evaluate_agent.py`, mixed provider/workspace/report lifecycle
in `evaluation_core.py`, multi-format cost/token fallback logic in
`evaluation_metrics.py`, and per-run `summary.html` creation in
`evaluation_report.py`. The new contracts directly address observed coupling.

The initial P0 plan nevertheless asks for broad concrete coverage at several
seams at once: two production challenge evaluators, several traffic profiles,
optional load refinement, multiple media views, rich aggregation, generic and
vendor harnesses, and extensive boundary schemas. That makes the skeleton
harder to finish without making it materially more extensible.

## Decision

Retain the known architectural contracts, but give each major seam exactly one
real P0-A implementation plus deterministic fakes or fixtures:

- One live SUT: Codex CLI + ChatGPT-managed access + `gpt-5.6-luna`.
- One complete challenge: Busy Intersection.
- One staged isolation implementation.
- One evaluator-controlled repair policy with at most two attempts.
- One Chromium/Playwright browser worker and one standardized animated capture
  with a poster image.
- One bounded held-stage load-to-failure policy with recovery.
- One local bundle inbox and safe `.ralph.zip` validator.
- One honest subscription-cost evidence path: unavailable cost plus preserved
  time, token, and attempt evidence.
- One small, visually coherent static comparison/detail site.

The 5x5 Rush remains a versioned public challenge design in P0-A. A topology
fixture must cross the same challenge and `traffic/v1` boundaries without a
conductor branch, but its live evaluator, private profiles, interchange checks,
and model run form P0-B.

Boundary contracts receive versioned schemas or envelopes. Internal objects do
not each receive a public interchange schema before a real boundary requires
one.

## Consequences

- P0-A proves a complete useful product loop rather than a partial loop across
  many variants.
- Fakes and conformance suites still prove that compatible adapters compose
  without vendor branches in the conductor or wizard.
- P0-B becomes an intentional challenge-generalization test: city logic must
  plug into the frozen challenge/evaluator seams.
- Animated human evidence remains in P0 because it is a product requirement,
  while extra viewpoints and side-by-side playback features are deferred.
- New real providers, local runtimes, browsers, storage backends, native loop
  tracks, and rich report interactions do not block the skeleton.

## Rejected alternatives

### Remove the abstractions until a second implementation exists

This would recreate already-observed legacy coupling and force known boundary
changes during migration.

### Implement both traffic challenges completely before an end-to-end release

This delays feedback on execution, evidence, bundling, cost, and reporting and
makes failures harder to localize.

### Make P0 fixtures-only

Fakes can prove contracts but cannot expose the authentication, event, process,
browser, and cost-evidence failures of a real SUT.
