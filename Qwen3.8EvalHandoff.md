# Ralph Bench: Qwen3.8 evaluation handoff

You are continuing Ralph Bench on a more capable machine. The purpose of this
handoff is to run the next serious local proving evaluation: Pi with the
installed pi-wiggum extension graph, a Qwen3.8-family model served locally by
the llama-swap stack in `../intel`, and the Busy Intersection challenge.

The expectation is that this model may clear the P0 working-solution bar. Do
not weaken that bar to make the run pass. A clean, diagnosable failure is still
useful evidence.

## Start here

1. Work in the repository root and read `AGENTS.md`, then at least:
   `docs/VISION.md`, `docs/P0_PLAN.md`, `docs/NEXT_STEPS.md`,
   `docs/CLI_AND_EXPERIMENTS.md`, `docs/ADAPTER_MODEL.md`,
   `docs/TRAFFIC_CHALLENGES.md`, `docs/TRAFFIC_CALIBRATION.md`,
   `docs/COLLISION_OBSERVATION.md`, `docs/MEASUREMENT_MODEL.md`,
   `docs/RESULT_BUNDLE.md`, and ADR 0014, ADR 0015, ADR 0016, and ADR 0017.
2. Check the worktree and recent history before changing anything. Preserve
   existing result bundles and unrelated user changes.
3. Run the unit/contract suite before a live evaluation:

   ```bash
   PYTHONPATH=src python3 -m unittest discover -s tests -q
   ```

4. Confirm that the local machine has enough memory and GPU/runtime capacity
   for the selected Qwen3.8 model. Discover the exact llama-swap model ID; do
   not assume that the display name `Qwen3.8` is the serving key.

## Non-negotiable preflight

The selected harness, extension graph, and local inference runtime must be
refreshed or explicitly proven current before model invocation. Do this before
the run, never during an active run:

- Refresh Pi with `pi update`.
- Refresh the installed Pi extension graph with `pi update --extensions`.
- Verify the `../intel` llama-swap binary identity with
  `/home/jeff/Code/intel/bin/llama-swap -version`.
- Verify proxy readiness with `GET http://127.0.0.1:8080/health`, enumerate the
  exact model IDs with `GET http://127.0.0.1:8080/v1/models`, and record the
  current lazy-loaded state from `GET http://127.0.0.1:8080/running`.
- Use a standalone Chrome/Chromium executable for the browser worker. On the
  proving host, `/snap/bin/chromium` is only a snap launcher and is not usable
  when snapd's AppArmor service is unavailable; `/opt/google/chrome/chrome`
  is the working evaluator executable.
- The user-level `llama-swap.service` owns server/model lifecycle. Ralph's
  llama-swap provider performs read-only readiness verification; the first Pi
  completion request triggers the selected alias to load through the proxy.
- Record the exact executable identities and versions. Never copy, print, or
  archive credentials.

If refresh, authentication, server startup, or model loading fails before a
candidate is produced or an evaluator starts, report the pre-evaluation
failure. Do not manufacture a diagnostic result bundle for that case.

## Evaluation target

The target is the existing P0 Busy Intersection vertical slice:

- `challenge = "busy-intersection/v1"`
- `provider = "llama-swap"`
- `client = "pi"`
- `track = "local"`
- `loop = "controlled"` for the first comparable proving run
- `scenario_pack = "traffic-intersection-p0a-calibrated"`

The controlled loop is intentionally the first target. Pi loads the installed
Wiggum guard extensions, while Ralph owns the bounded repair loop and supplies
browser/runtime feedback. This is a Pi/Wiggum composition, but it is not a
claim about the native Wiggum TPM workflow. `loop = "native"` is a distinct
follow-up experiment and must not be mixed into the controlled-loop metrics.

Create a local, ignored experiment TOML using the exact discovered model ID and
the resolved Pi executable. For this reasoning-heavy model, use the explicit
expanded proving budget below:

```toml
schema_version = "experiment/v1"
name = "pi-qwen3.8-working-solution"
challenge = "busy-intersection/v1"
client = "pi"
provider = "llama-swap"
model = "<exact llama-swap model ID>"
track = "local"
repetitions = 1

[client_options]
reasoning_effort = "high"
loop = "controlled"
executable = "<resolved Pi executable>"

[budget]
max_wall_seconds = 3600
max_attempts = 2

[evaluation]
scenario_pack = "traffic-intersection-p0a-calibrated"

[output]
inbox = "results/inbox"
```

Run it with the repository environment, for example:

```bash
export LLAMA_SWAP_EXECUTABLE=/home/jeff/Code/intel/bin/llama-swap
export RALPH_BENCH_CHROMIUM=/opt/google/chrome/chrome
PYTHONPATH=src python3 -m ralph_bench run experiments/pi-qwen3.8-working-solution.toml
```

Use the current harness/provider implementation and its preflight rather than
manually bypassing the conductor. If the stronger machine requires a changed
context, output, reasoning, or wall-time setting, make that change explicit in
the experiment and preserve it as provenance; do not silently alter the
comparison. The local proving experiment may use an expanded model-work budget
for Qwen reasoning and a larger local-provider completion allowance. The
evaluator interface and evaluator-owned demand requirements are unchanged;
collision evidence is still required when requested, but its graduated safety
score is reported separately from functional eligibility and throughput.

The public challenge prompt now makes several previously implicit requirements
explicit: evaluator IDs must be preserved byte-for-byte with no `eval_` prefix,
callbacks must be registered before the animation loop with initialization
queueing, vehicle bodies must stay inside legal road/lane corridors, pedestrians
must stay on sidewalks or their requested crossings, and the page must be
checked for runtime errors before completion. It also explicitly requires that
`observe()` omit demo IDs and that evaluator vehicle paths begin at the outer
requested entrance and end beyond the outer requested exit; a prior Qwen repair
used an internal 35-unit path against a 42-unit finish boundary and never
finished a car. Treat these as hard implementation invariants; do not satisfy
them by hiding demo traffic or weakening evaluator checks. The prompt now asks
for a compact artifact (under 16,000 bytes) to reduce syntax and verification
risk on the local thinker.

The latest diagnostic run also exposed two generated JavaScript pitfalls: the
first attempt called `.at()` on a traveler object rather than an array, and its
repair declared `eval` in strict mode. The prompt now calls these out directly
and asks for strict-mode-safe, compact JavaScript. The following run then used
an overcomplicated route library with an undefined direction lookup and an
uninitialized pedestrian position; the prompt now asks for defensive callback
normalization, initialized state, and simple explicit polylines. The next run
completed all evaluator travelers with no browser errors, but still failed
because the artifact called Ralph finish/observe APIs for demo IDs; the prompt
now makes evaluator-supplied traffic the only moving traffic by default, puts
optional demo mode behind an off switch, and makes the register/queue/finish/
observe lifecycle explicit. This should remove the main ambiguity instead of
asking the model to maintain two traffic domains during its first write.

The prompt now also spells out the composite pedestrian direction values and
the recordable trip lifecycle. It gives a conservative collision strategy:
distance-based following, central-junction reservation, car yielding to active
crosswalk users, and at most one evaluator car in the central conflict zone.
This is intentionally biased toward functional eligibility before throughput.

The latest run confirmed the interface and runtime guidance but exposed a
movement deadlock: the repair rejected every pedestrian because it required the
two endpoints of a composite direction to be equal, and its car conflict check
treated all queued cars as blockers before any car could enter. The next prompt
revision simplifies this to a liveness-first controller: one FIFO evaluator-car
queue with one global junction reservation, and one FIFO pedestrian queue with
one active crossing at a time. The queue head alone enters; later cars wait
outside; the reservation is released at the requested outer exit. Pedestrians
split `direction` at `-to-`, validate the crossing pair, cross to the opposite
sidewalk, and never get rejected merely because the endpoints differ. Signals
remain visual communication, not the only movement permission.

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
- report evaluator-issued bodies through `RalphGates.observe()` at the required
  cadence with truthful, complete body evidence and the strongest practical
  safety score; collisions are scored separately and must never be hidden;
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
- `qwen3.8-27b-think` was retested with an explicit gates/v1 API example, a
  simplified non-blocking implementation target, high reasoning, a 3,600-second
  wall budget, and a 32,768-token local completion allowance. The final artifact
  registered callbacks, delivered all 73 arrivals, and produced valid finish
  notifications with no runtime or network violations. It still failed the
  traffic bar: 30/60 cars completed and 0/13 pedestrians. Its validated
  diagnostic evidence is
  `results/inbox/df5b403f-9892-4e5e-8a2d-b2316c4b2d1d.ralph.zip`.

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
