# ADR 0006: Centralize Configuration Ownership and Lifecycle

**Status:** Proposed
**Date:** 2026-08-23

## Context

The legacy evaluator configured LM Studio and individual harnesses through a
mixture of command flags, environment variables, generated files, user-global
files, and assumed machine state. Provider setup was sometimes embedded in
harness-specific paths. The result was difficult to reproduce, audit, restore,
and extend consistently.

Ralph Bench must support multiple clients and providers without multiplying
configuration strategies or silently inheriting unrelated user settings.

## Decision

The conductor owns a single normalized configuration lifecycle. A validated
experiment describes requested intent. A provider adapter exclusively owns
provider/runtime setup and observation. A harness adapter exclusively renders
its scoped native client connection and controls. The conductor resolves,
orders, verifies, records, and cleans up those actions transactionally.

Interactive discovery informs the experiment but does not mutate configuration
or become an implicit execution input. User-global configuration is not
silently inherited. Requested, materialized, effective, and cleanup states are
recorded separately with secrets redacted.

For LM Studio specifically, harness adapters consume a resolved provider
endpoint/model plan; they do not independently configure LM Studio.

## Consequences

- Adding a client does not add another LM Studio lifecycle implementation.
- Runs have one inspectable requested configuration and explicit effective
  evidence.
- Scoped configuration and cleanup become testable adapter contracts.
- Provider setup can fail or be restored independently of client execution.
- Some clients may require additional scoped-home work or expose lower
  reproducibility when global state cannot be avoided.
- The conductor and adapters need more structure than a single command string,
  but avoid accumulating incompatible one-off configuration code.

## Rejected alternatives

### Let each harness adapter configure its provider

Locally convenient but duplicates provider behavior, creates inconsistent
defaults, and reproduces the legacy mishmash.

### Reuse whatever user-global configuration already works

Reduces initial setup code but makes results machine-state-dependent, risks
credential exposure, and undermines idempotence.

### Have the wizard write native client/provider files directly

Mixes safe authoring with state mutation and creates a second lifecycle outside
the conductor's evidence and rollback boundary.
