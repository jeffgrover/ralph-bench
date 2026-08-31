# ADR 0016: Use a bounded Pi handoff for the first local proving run

**Status:** Accepted for the P0 local proving path  
**Date:** 2026-08-30

## Context

Pi-wiggum is an installed Pi extension graph, not a separate client. Its TPM
prompt template is useful for an interactive human conversation, but a small
local model can spend its entire bounded generation narrating the plan or
repeating an incomplete structured `write` call. That prevents Ralph from
evaluating the artifact and makes the local harness seam appear broken when
the failure is actually model/tool-call calibration.

The P0 controlled loop also needs browser/runtime results before its one repair
attempt. A candidate that reaches evaluation must remain reportable even when
the repair process times out or leaves the artifact unchanged.

## Decision

For `client_options.loop = "controlled"` with Pi:

- Refresh Pi and its installed extension graph as usual.
- Load the installed Wiggum guard extensions, but do not load the Wiggum TPM
  prompt template. The native template remains enabled for `loop = "native"`.
- Use a short adapter-owned implementation handoff and a narrow `write` tool
  surface for the first local proving calibration.
- Materialize a scoped LM Studio model descriptor with bounded context/output
  settings and disable the local HTTP idle timeout.
- Stop the Pi child process when a new or changed `index.html` is written.
  An existing first-attempt file is not sufficient to terminate a repair
  attempt.
- Run static and browser evaluation inside the controlled public-check
  boundary. Return stable, semantic failure guidance to the repair prompt;
  do not pass private schedule values or scoring thresholds.
- If a repair attempt does not produce an evaluable replacement, preserve the
  last candidate that did reach browser evaluation and its evidence as the
  failed run outcome.

This is still a Pi/Wiggum local proving composition, but it is explicitly a
Ralph-controlled loop. Native Wiggum continuation and Ralph repair are not
collapsed into one metric or one control path.

## Consequences

- Small local models get a realistic chance to produce an artifact within the
  model-work budget, and post-write narration is not mistaken for useful work.
- Browser failures can inform the single repair pass without leaking private
  demand or scoring details.
- A controlled Pi result is not a claim about the quality of the native Wiggum
  TPM workflow; those modes remain separately identifiable.
- The first Gemma proving run remains an honest below-bar result when it cannot
  complete a passing artifact. A failing or incomplete local run is not turned
  into a synthetic result bundle.
