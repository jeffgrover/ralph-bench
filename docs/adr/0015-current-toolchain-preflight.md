# 0015 — Current toolchain preflight before evaluation

**Status:** Accepted
**Date:** 2026-08-30

## Context

Ralph Bench evaluates a complete model-and-harness system, so the exact
harness and local inference runtime are part of the system under test. A stale
client, extension, or inference runtime can make a result difficult to
interpret and can cause a failure before the benchmark reaches the artifact or
traffic questions it is meant to answer.

The installed tools expose different update surfaces. Codex provides
`codex update`; Pi provides `pi update` and `pi update --extensions`; LM Studio
provides `lms runtime update` for installed inference runtime extensions, plus
server and model lifecycle commands. The `lms` CLI does not provide a desktop
application update command.

## Decision

Every model evaluation begins with a bounded, conductor-owned current-toolchain
preflight after the experiment has been resolved and before the first model
invocation:

1. The selected harness is detected and updated through its documented update
   command where supported (`codex update`, or `pi update` followed by
   `pi update --extensions`).
2. A local provider updates its installed inference runtime where supported
   (`lms runtime update --all --yes`).
3. The provider is prepared transactionally. LM Studio observes
   `lms server status --json`, starts the server when it was stopped, loads the
   selected model when it was not already loaded, and verifies the effective
   state through `lms ps --json`. The provider returns an idempotent rollback
   handle that unloads only a model introduced by the run and stops only a
   server started by the run.
4. The exact executable identity, before/after tool versions, extension
   identities, runtime/server/model identities, update outcomes, and any
   unsupported freshness claims are recorded as redacted provenance.

Discovery, the wizard, and `rb doctor` remain read-only. Updates and provider
preparation occur only in run preflight, never during an active model or
browser-evaluation phase. Provider mutations are owned by the provider adapter,
registered for cleanup, and must not be hidden inside a harness adapter.

For Pi-wiggum, Wiggum is a Pi extension and therefore part of the native Pi
harness composition. Its internal repair iterations are recorded as native
harness evidence and count against the same bounded model-work budget. They
are not silently relabeled as Ralph-controlled repair passes.

The LM Studio desktop application version is recorded when observable. Because
the `lms` CLI has no desktop-app update operation, an unavailable app-freshness
check is explicit operator-visible evidence rather than an invented claim that
the application is current.

If current-toolchain or provider readiness fails before a candidate is
preserved or evaluation starts, the run fails fast without a diagnostic result
bundle. A preserved candidate that reaches evaluation retains a normal result
bundle even when the candidate or evaluation fails.

## Consequences

- “Latest” is a reproducible preflight policy with before/after evidence, not
  an assumption based on whatever happened to be on `PATH`.
- Harness extensions and their dependencies are part of harness provenance.
- Local model results identify both the serving runtime and the selected model,
  not only the model string passed to the client.
- Provider preparation is transactional: a failed setup still exposes its
  cleanup handle, and a successful evaluation restores provider state before
  the conductor returns.
- A provider can expose a limitation when its platform cannot update or verify
  a component; Ralph does not silently substitute a different provider or
  claim freshness it cannot observe.
- Native Wiggum execution and evaluator-controlled Ralph repair remain
  separate loop modes and are compared only with their budgets and evidence
  made explicit.
