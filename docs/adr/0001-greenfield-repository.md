# ADR 0001: Greenfield Repository

**Status:** Proposed
**Date:** 2026-08-23

## Context

The legacy evaluation suite contains valuable runner adapters, event fixtures,
safety behavior, reports, and a large result corpus. It also couples run
identity to directory names, overwrites repetitions, generates reports during
execution, reconstructs metadata from HTML, and stores references/results near
agent workspaces.

The new benchmark changes the fundamental run, challenge, evidence, isolation,
measurement, and reporting contracts.

## Decision

Implement Ralph Bench in an independent repository and Git history. Treat the
legacy repository as a read-only research source and future migration input.
Port proven behavior selectively behind the new contracts rather than copying
the architecture wholesale.

## Consequences

### Positive

- New contracts do not need backward-compatible directory or report behavior.
- Hidden material and reference solutions can be separated from the start.
- Repetitions, bundles, and challenge schemas become foundational concepts.
- Legacy code can be ported only after its responsibility is understood.

### Negative

- Some mature runner and platform handling must be reintroduced deliberately.
- The two repositories coexist until a legacy importer and transition policy
  exist.
- Initial feature coverage will be smaller.

## Rejected alternatives

- Build vNext in a subdirectory and extract it later.
- Use a long-lived branch of the legacy repository.
- Preserve legacy result directories as the canonical P0 storage format.
