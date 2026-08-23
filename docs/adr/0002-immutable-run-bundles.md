# ADR 0002: Immutable Run Bundles

**Status:** Proposed
**Date:** 2026-08-23

## Context

Generating per-run HTML during execution couples evidence collection to one
presentation, duplicates artifacts, makes remote ingestion fragile, and
encourages reporters to mutate or truncate source files.

Ralph Bench must support repetitions, multiple machines, future remote stores,
recalculated reports, and forensic inspection.

## Decision

Every run produces one versioned, checksummed `.ralph.zip` bundle containing
raw and canonical evidence, the selected artifact, evaluation results,
provenance, and captures. Reporting is a read-only transform over validated
bundles and writes outside them.

Run identity and metadata come from manifests, never from filenames or HTML.

## Consequences

### Positive

- A bundle is portable across machines and storage backends.
- Reporting can be redesigned without rerunning agents.
- Evidence integrity and duplicate detection are explicit.
- Remote ingestion can be idempotent and content-addressed.
- Source evidence is not shortened to satisfy site-hosting constraints.

### Negative

- Bundle schema evolution and validation require up-front design.
- Raw vendor traces can be large.
- Public and forensic visibility tiers may eventually require separate bundles.
- The reporter needs a catalog/cache rather than scanning arbitrary directories.

## Rejected alternatives

- Keep run directories as the official interchange format.
- Include a generated `summary.html` as authoritative metadata.
- Allow reporters to rewrite oversized raw evidence.
