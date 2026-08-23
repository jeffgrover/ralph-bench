# ADR 0007: Compose the SUT from Polymorphic Adapter Families

**Status:** Accepted
**Date:** 2026-08-23

## Context

Ralph Bench evaluates a cross-product of agentic harnesses, local and cloud
providers, and rapidly changing models. Encoding each supported combination as
a dedicated runner or scattering vendor-name conditionals through the wizard,
conductor, and reporter would make support expensive and reproduce the coupling
of the legacy evaluator.

Harnesses, providers, and models also have different responsibilities. Treating
them as one generic plugin interface would hide important lifecycle and
configuration boundaries.

## Decision

Define three independently registered, typed polymorphic protocols:
`HarnessAdapter`, `ProviderAdapter`, and `ModelAdapter`. A capability resolver
composes one of each into a versioned `ResolvedSUT` using connection protocols,
option schemas, model offers, capabilities, and explicit compatibility rules.

The CLI term for a harness is `client`. Most model implementations are
declarative descriptors interpreted by a generic adapter; specialized code is
used only where behavior requires it. Unknown models receive conservative
unknown capabilities rather than invented metadata.

P0 uses a validated built-in registry. Arbitrary third-party dynamic loading is
deferred until the contracts and security boundary are proven.

## Consequences

- Adding a compatible harness, provider, or model normally changes only its
  adapter/descriptor and fixtures.
- The conductor and wizard operate on protocols and `ResolvedSUT`, not vendor
  branches.
- Capability negotiation can explain why combinations or controls are
  unavailable.
- Cloud composition also negotiates raw usage/billing/reference evidence. A
  provider-billed amount, an OpenRouter-equivalent reference, and unavailable
  evidence remain distinct and cannot silently become zero.
- Shared conformance suites can enforce discovery, redaction, planning,
  evidence, timeout, and cleanup behavior.
- Typed protocols and descriptors require more up-front design than accepting
  arbitrary command strings, but avoid a combinatorial adapter matrix.
- Vendor quirks still exist, but must be isolated in explicit tested rules or
  namespaced adapter extensions.

## Rejected alternatives

### One runner per harness-provider-model combination

Produces a combinatorial implementation and inconsistent behavior across
nearly identical combinations.

### Vendor conditionals in the conductor and wizard

Initially fast but makes central orchestration depend on every integration and
prevents independent evolution.

### One universal adapter protocol

Superficially uniform but conflates harness execution, provider lifecycle, and
model metadata/control resolution.

### One code class per model ID

Creates needless class and maintenance volume. Declarative model descriptors
plus a conservative generic model adapter cover the common case.
