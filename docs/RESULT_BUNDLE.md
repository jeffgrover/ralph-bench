# Immutable Result Bundle

**Status:** Accepted
**Date:** 2026-08-23
**Proposed extension:** `.ralph.zip`

## Purpose

A result bundle is the immutable, portable evidence produced by one run. It is
the only input required by downstream validation, aggregation, judging, and
static reporting, apart from explicitly versioned external judge material.

The run process does not generate `summary.html`. HTML, thumbnails optimized
for the site, aggregate tables, and indexes are derived outputs stored outside
the bundle.

## Core requirements

- One bundle per run/repetition.
- Globally unique run ID independent of filenames.
- Explicit schema versions.
- Complete SUT, environment, challenge, attempt, and metric provenance.
- Raw vendor evidence retained without destructive truncation.
- Credentials and sensitive values redacted before finalization.
- Cryptographic inventory covering every file.
- Safe validation before extraction or ingest.
- Finalized bundles are never modified in place.
- Transport metadata such as a Google Drive ID is external and does not mutate
  the bundle.

## Proposed layout

```text
<run-id>.ralph.zip
├── run.json
├── experiment.json
├── challenge.json
├── prompt.txt
├── metrics.json
├── cost.json
├── failures.json
├── events/
│   ├── canonical.jsonl
│   └── raw/
├── attempts/
│   ├── attempt-001/
│   │   ├── attempt.json
│   │   ├── prompt.txt
│   │   ├── feedback.json
│   │   └── public-checks.json
│   └── attempt-002/
├── evaluation/
│   ├── assertions.json
│   ├── scenarios/
│   ├── capacity-curve.json
│   └── runtime-observations.json
├── artifact/
│   └── submission/
├── captures/
│   ├── overview.webm
│   ├── overview.png
│   └── interchange.webm       # optional P0-B city profile
├── provenance/
│   ├── environment.json
│   ├── hardware.json
│   ├── software.json
│   ├── client.json
│   ├── provider.json
│   ├── model.json
│   ├── sut-resolution.json
│   ├── configuration.json
│   ├── isolation.json
│   └── redaction.json
└── checksums.sha256
```

Files that do not apply may be absent only when the schema explicitly permits
it. Absence must not be confused with a measured zero.

### P0-A bundle profile

The layout above is the durable namespace, not a requirement to implement
every future evidence variant immediately. P0-A requires one complete profile:
run/experiment/challenge manifests, prompt, metrics/cost/failures, raw and
canonical harness evidence, preserved attempts, the selected artifact,
assertions and the bounded capacity curve, one animated overview plus poster,
consolidated provenance, inventory, and checksums. Extra viewpoints, encrypted
public/private tiers, remote transport records, and exhaustive internal schemas
are deferred.

## `run.json`

The manifest should include:

- Bundle/run schema version.
- Run ID and experiment ID.
- Parent/repetition identity.
- Created/finalized timestamps.
- Challenge and judge-pack identifiers/versions.
- SUT identity:
  - model
  - client/harness and version
  - provider and service tier
  - authentication mode, billing mode, cost policy/status, and provenance,
    without account secrets
  - harness/provider/model adapter IDs and versions
  - negotiated protocol/capability versions
  - requested/effective configuration summary
  - effort and tool policy
- Run validity and outcome.
- Attempt count and selected candidate hash.
- Terminal reason.
- Isolation level.
- Metric-quality summary.
- Inventory references.

Directory names and filenames are display conveniences; they are never parsed
to reconstruct identity.

`provenance/configuration.json` preserves redacted authored, resolved,
materialized, effective, and cleanup state as distinct sections. It includes
generated configuration hashes, environment key names, command shape,
requested/effective mismatches, restoration results, and confidence. It never
contains raw credentials, copied user-global configuration, or an archived
scoped home.

`provenance/sut-resolution.json` records the independently selected adapter
descriptors, provider model offer, canonical or generic model match,
capability-negotiation evidence, namespaced options, and structured warnings.
Reports use these explicit identity fields rather than adapter class names.

For the P0 ChatGPT-backed path, provider evidence records that Codex reported
ChatGPT-managed authentication and that billing uses a flat subscription. It
does not archive authentication caches, tokens, or account identifiers.
`cost.json` preserves the declared experiment-scoped pool cost/period, expected
run membership and digest, chargeable-attempt evidence, provisional/incomplete
status, and any separately labeled raw cash, credit, token, or API list-price-
equivalent evidence. The disposable catalog derives final allocated
subscription USD after it validates complete pool membership. See
[`COST_MODEL.md`](COST_MODEL.md).

## Canonical events

`events/canonical.jsonl` is an append-oriented normalized timeline. Events use
a stable envelope such as:

```json
{
  "schema_version": "event/v1",
  "sequence": 42,
  "time_monotonic_ms": 18342,
  "phase": "agent",
  "attempt": 1,
  "type": "tool.completed",
  "source": "harness",
  "payload": {}
}
```

Wall timestamps may be included for human correlation, but ordering and
durations use monotonic time when captured by the evaluator.

Vendor-native streams remain under `events/raw/`. Canonicalization does not
destroy or replace them.

## Attempts

Each attempt has a stable manifest containing:

- Attempt number/ID.
- Start/end/terminal reason.
- Input prompt or structured feedback hash.
- Resource usage with provenance.
- Candidate tree hash.
- Public-check results.
- Whether another attempt was authorized and why.

Candidate snapshots may be stored per attempt when needed for reproducibility,
or content-addressed with explicit references to avoid needless duplication.
P0 may retain full snapshots for simplicity.

## Artifact

`artifact/submission/` contains only the candidate being judged, not conductor
files, hidden tests, credentials, or reporter output. Its complete tree hash is
recorded in `run.json` and the checksum inventory.

The artifact must remain runnable after safe extraction with no network. P0-A
requires every runtime dependency actually used by the candidate—including
challenge-supplied browser libraries—to be copied into
`artifact/submission/`. A manifest lists their source challenge version and
digests; the reporter does not fetch or reconstruct missing dependencies.

## Capture evidence

Every capture record identifies the evaluated artifact tree hash, challenge,
scenario/profile, seed, simulation interval and phase, playback rate, duration,
frame rate, viewport, browser/Playwright versions, and capture-worker version.
The overview poster and animation must be produced from the same evaluated
artifact and requested scenario. Media is human-review evidence, not an
authoritative traffic counter.

## Evaluation evidence

Evaluation records include:

- Structured assertions and evidence paths.
- Scenario/profile/seed.
- Requested trip manifest hash.
- Capacity stages and refinement runs.
- Snapshots/events used for metric derivation.
- Runtime/browser observations.
- Failure windows and thresholds.

Private scenario values may be included in a locally retained forensic bundle
but omitted or encrypted in a public distribution bundle. If two bundle tiers
are introduced, they must be separately hashed artifacts with explicit
visibility types rather than post-finalization mutation.

## Metrics and failures

Every metric record includes ID/version, numeric value, unit, provenance,
quality label, scenario/attempt scope, and evidence references. Cost fields use
decimal strings or integer micros and explicit nulls so missing evidence cannot
collapse to floating-point zero.

Every failure record includes stable taxonomy code, severity, stage, detector,
human-readable summary, and evidence references. Natural-language flags alone
are insufficient.

## Redaction

Before bundle finalization, inspect and redact:

- API keys and bearer tokens.
- Authentication files.
- Provider cookies/session tokens.
- Sensitive environment variables.
- User-identifying absolute paths where not required.
- Private challenge material not intended for the selected bundle tier.

Redaction actions are summarized in `provenance/redaction.json` without
reproducing the secret value. The raw agent workspace is not automatically safe
to archive.

## Finalization

Proposed finalization sequence:

1. Stop all agent and logging processes.
2. Select and hash the final candidate.
3. Complete evaluation records.
4. Collect/redact provenance and raw evidence.
5. Validate schemas and internal references.
6. Write a lexically ordered inventory.
7. Compute SHA-256 checksums for every payload file.
8. Create the ZIP in a temporary location.
9. Reopen and validate the ZIP independently.
10. Atomically move it into the local results inbox.

The final bundle must not depend on a `complete` filename convention alone;
its manifest and checksum inventory establish completeness.

## Validator requirements

The validator must defend against:

- Absolute paths and `..` traversal.
- Backslash traversal variants.
- Symlinks and special files.
- Duplicate or case-colliding entries.
- Unexpected compression methods.
- Excessive entry count.
- Per-file and total expanded-size limits.
- Suspicious compression ratios.
- Missing/unknown schema versions.
- Missing inventory entries and checksum mismatches.
- References to absent evidence.
- Unrecognized required feature flags.

Invalid bundles are quarantined with structured reasons and never silently
enter official reports.

## Ingest and reporting

`rb build` follows a read-only transform:

```text
bundle inbox -> validate -> catalog/cache -> derived site
```

The catalog is rebuildable. Deleting it must not lose authoritative evidence.
The reporter may copy or transform selected captures and artifacts into `site/`
but never edits the bundle. `rb build` closes a P0 subscription pool only when
all expected terminal run IDs are present exactly once with matching pool
declarations, complete non-contradictory charge evidence and cost provenance,
and a nonzero chargeable-attempt total. It then produces a versioned derived
catalog/report value from immutable `cost.json` inputs; it does not rewrite
source bundles.

Candidate HTML/JavaScript is untrusted. The derived static site must not inject
or execute it in the report DOM. P0-A embeds only trusted evaluator-produced
poster/video media and offers the self-contained artifact as an explicit
download. Running it is outside the static report security boundary. Malicious
markup/script/navigation fixtures must remain inert in report generation.

## Future transport

The storage interface will eventually support local directories, Google Drive,
and possibly other object stores. Transport is intentionally outside P0. A
future backend should use the run ID and bundle digest for idempotence, upload
to a temporary/staging object, verify the remote digest, and only then publish
it as complete.
