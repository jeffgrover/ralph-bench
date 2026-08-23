# ADR 0005: Use `rb` with Guided Experiment Authoring

**Status:** Proposed
**Date:** 2026-08-23

## Context

Ralph Bench must be easy to operate across changing local hardware, clients,
providers, and model inventories. Requiring users to remember identifiers and
hand-author every TOML file makes the common path fragile. Conversely, a purely
interactive runner would obscure effective settings and make experiments hard
to reproduce or automate.

Clients do not expose provider and model discovery uniformly. Discovery can be
complete, partial, stale, or unavailable, and cloud probes must not incur
unannounced generation cost.

## Decision

The installed command is `rb`.

In an interactive terminal, `rb` with no arguments starts a client-first
experiment wizard. It uses adapter/provider capability probes to suggest
providers, models, and supported controls; displays the source of defaults;
allows manual fallback; validates the result; writes an experiment TOML file;
and offers to run it.

Interactive authoring ends at the validated TOML file. Explicit
`rb run <experiment.toml>` execution is deterministic with respect to that
file and runtime preflight and does not consult remembered wizard choices.

Discovery probes are read-only, bounded, non-generation operations. They never
store credentials in TOML and report partial or unavailable capabilities
honestly.

## Consequences

- The common workflow can begin with one short command and no memorized flags.
- Generated experiments remain inspectable, editable, versionable, and
  suitable for unattended reruns.
- Harness, provider, and model adapters need capability/discovery boundaries
  in addition to execution.
- P0 requires a testable interactive state machine, TOML writer, and fake
  probes before real client integration.
- Universal provider/model enumeration is not promised; manual entry is part
  of the normal contract.
- Wizard convenience state must be isolated from authoritative run inputs.

## Rejected alternatives

### Name the executable `ralph`

Readable, but less convenient for a command expected to be invoked frequently.
`python -m ralph_bench` remains an unambiguous fallback if `rb` conflicts with
an existing executable.

### Require hand-written TOML

Simple to implement, but imposes avoidable discovery and syntax work on every
experiment and makes multi-client operation error-prone.

### Run directly from transient interactive answers

Convenient for a single invocation, but creates a second, less reproducible
configuration path and makes it harder to inspect what was actually requested.

### Guarantee discovery for every client and provider

Not technically credible. A capability-based result with clear provenance and
manual fallback is more robust than stale catalogs or fragile undocumented
parsing.
