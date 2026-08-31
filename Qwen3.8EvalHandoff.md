# Ralph Bench: Qwen3.8 evaluation handoff

You are continuing Ralph Bench on a more capable machine. The purpose of this
handoff is to run the next serious local proving evaluation: Pi with the
installed pi-wiggum extension graph, a Qwen3.8-family model served locally by
LM Studio, and the Busy Intersection challenge.

The expectation is that this model may clear the P0 working-solution bar. Do
not weaken that bar to make the run pass. A clean, diagnosable failure is still
useful evidence.

## Start here

1. Work in the repository root and read `AGENTS.md`, then at least:
   `docs/VISION.md`, `docs/P0_PLAN.md`, `docs/NEXT_STEPS.md`,
   `docs/CLI_AND_EXPERIMENTS.md`, `docs/ADAPTER_MODEL.md`,
   `docs/TRAFFIC_CHALLENGES.md`, `docs/MEASUREMENT_MODEL.md`,
   `docs/RESULT_BUNDLE.md`, and ADR 0014, ADR 0015, and ADR 0016.
2. Check the worktree and recent history before changing anything. Preserve
   existing result bundles and unrelated user changes.
3. Run the unit/contract suite before a live evaluation:

   ```bash
   PYTHONPATH=src python3 -m unittest discover -s tests -q
   ```

4. Confirm that the local machine has enough memory and GPU/runtime capacity
   for the selected Qwen3.8 model. Discover the exact LM Studio model ID; do
   not assume that the display name `Qwen3.8` is the serving key.

## Non-negotiable preflight

The selected harness, extension graph, and local inference runtime must be
refreshed or explicitly proven current before model invocation. Do this before
the run, never during an active run:

- Refresh Pi with `pi update`.
- Refresh the installed Pi extension graph with `pi update --extensions`.
- Refresh the installed LM Studio inference runtime where supported with
  `lms runtime update --all --yes`.
- Verify LM Studio server readiness with `lms server status --json`.
- Verify the exact selected model is loaded and ready with `lms ps --json`.
  Start the server or load the model only through the Ralph provider lifecycle
  when using `rb run`, so the provider can record and roll back its changes.
- Record the exact executable identities and versions. Never copy, print, or
  archive credentials.

If refresh, authentication, server startup, or model loading fails before a
candidate is produced or an evaluator starts, report the pre-evaluation
failure. Do not manufacture a diagnostic result bundle for that case.

## Evaluation target

The target is the existing P0 Busy Intersection vertical slice:

- `challenge = "busy-intersection/v1"`
- `provider = "lm-studio"`
- `client = "pi"`
- `track = "local"`
- `loop = "controlled"` for the first comparable proving run
- `scenario_pack = "traffic-intersection-p0a"`

The controlled loop is intentionally the first target. Pi loads the installed
Wiggum guard extensions, while Ralph owns the bounded repair loop and supplies
browser/runtime feedback. This is a Pi/Wiggum composition, but it is not a
claim about the native Wiggum TPM workflow. `loop = "native"` is a distinct
follow-up experiment and must not be mixed into the controlled-loop metrics.

Create a local, ignored experiment TOML using the exact discovered model ID and
the resolved Pi executable. Start with the current comparable budget:

```toml
schema_version = "experiment/v1"
name = "pi-qwen3.8-working-solution"
challenge = "busy-intersection/v1"
client = "pi"
provider = "lm-studio"
model = "<exact LM Studio model ID>"
track = "local"
repetitions = 1

[client_options]
reasoning_effort = "none"
loop = "controlled"
executable = "<resolved Pi executable>"

[budget]
max_wall_seconds = 900
max_attempts = 2

[evaluation]
scenario_pack = "traffic-intersection-p0a"

[output]
inbox = "results/inbox"
```

Run it with the repository environment, for example:

```bash
PYTHONPATH=src python3 -m ralph_bench run experiments/pi-qwen3.8-working-solution.toml
```

Use the current harness/provider implementation and its preflight rather than
manually bypassing the conductor. If the stronger machine requires a changed
context or output setting, make that change explicit in the experiment and
preserve it as provenance; do not silently alter the comparison.

## What counts as success

The primary question is functional: can the model produce an original browser
artifact that implements a working Busy Intersection simulation through the
public `gates/v1` contract?

The candidate must, in substance:

- register the evaluator-injected arrival and finish callbacks;
- accept and service evaluator-owned demand rather than choosing its own
  workload;
- report valid completion identities and finish notifications;
- remain stable during the recorded offline browser run;
- complete the required functional/warmup/recovery behavior for the evaluated
  profile; and
- preserve a coherent, usable, visually understandable simulation.

Functional eligibility comes before performance comparison. Once a candidate
is a working solution, throughput, capacity, latency, backlog, and recovery
differentiate it from other eligible models. There is no P0 composite overall
score, and high throughput must not compensate for an invalid or dishonest
artifact.

The evaluator owns gate IDs, authoritative timestamps, demand, completion
validation, and outstanding-demand monitoring. Do not add candidate-authored
topology, snapshot, queue, simulation-clock, or event protocols to the
challenge in order to accommodate a model.

## Evidence and failure handling

- Every evaluated repetition must retain one immutable, checksummed `.ralph.zip`
  bundle. Do not overwrite or delete earlier evidence.
- A candidate that reaches static or browser evaluation gets a bundle even if
  evaluation fails. A complete pre-evaluation failure with no candidate or no
  started evaluator gets no diagnostic bundle.
- Inspect the final bundle manifest, preflight, attempts, evaluator assertions,
  metrics, cost evidence, and raw browser/agent evidence. The local cost status
  should be unavailable with `billing_mode = "local"`, not zero or a fabricated
  dollar amount.
- Use `rb preview` only to inspect the evaluator-recorded WebM; do not execute
  candidate HTML as a substitute for the recorded evaluation.
- Treat a below-bar result as a result. Distinguish model limitations from
  harness/provider defects, evaluator defects, and operator/environment
  failures.

The previous local trials are calibration, not baselines to hide:

- `gemma-4-12b-it-mlx` did not complete a passing repair within the bounded
  local budget.
- `gpt-oss-20b` reached both static and browser evaluation in two attempts, but
  registered no gates and serviced no evaluator demand. Its corrected evidence
  is `results/inbox/e23f4a21-17a2-48ab-a3ec-38f420192812.ralph.zip`.

## If the run passes

Report the run ID and bundle path, exact model/toolchain/runtime identities,
attempt count and wall time, functional assertion results, and the separate
performance measurements. Preview the recorded overview and note any visible
quality issues without collapsing them into the functional or throughput
measurements.

Do not immediately broaden the challenge, add a composite score, or treat one
passing local run as a general ranking. First preserve the evidence and compare
the result only along the documented eligibility and performance dimensions.

## If the run fails

Classify the failure from evidence before editing code. In particular, check
whether the candidate reached evaluation, whether the public gates were
registered, whether browser/runtime errors are real, and whether the model
spent its budget in tool-call or post-write narration. Preserve the bundle and
raw evidence. Only fix a repository seam when the evidence identifies a real
Ralph defect; add a regression test, rerun the full suite, and document the
change before attempting another live run.

The next engineering work after a credible Qwen3.8 result remains seam-first:
functional eligibility, the agent-runnable public conformance check, the fair
acceptance/repair loop, and the generic challenge execution boundary. Do not
start the future city implementation just because this run is successful.
