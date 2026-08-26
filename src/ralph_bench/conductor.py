"""The complete P0-A Codex → gates evaluation → bundle vertical slice."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import sys
import tempfile
import threading
import time
from typing import Any

from .adapters import (
    AdapterRegistry,
    CodexAttemptExecutor,
    InvocationPlan,
    ResolvedSUT,
    credential_secret_values,
)
from .browser_runtime import (
    find_chromium,
    find_playwright_browsers_path,
    run_browser_evaluation,
)
from .bundle_materialization import (
    AttemptBundleEvidence,
    RunBundleEvidence,
    finalize_run_bundle,
)
from .costs import CostEvidence
from .events import EventRecorder
from .execution import (
    AttemptStore,
    ControlledAttemptLoop,
    HarnessAttemptResult,
    InvocationAdmission,
    PublicCheckResult,
    candidate_tree_hash,
    expand_repetitions,
)
from .experiments import Experiment, experiment_to_dict
from .isolation import (
    CanaryStatus,
    NetworkCapability,
    StagedWorkspace,
    build_isolation_report,
    build_process_environment,
)
from .gate_evaluator import check_static_candidate
from .gates import balanced_seed_for_repetition, build_balanced_gate_scenario


class ConductorError(RuntimeError):
    """Infrastructure prevented an evaluation from producing valid evidence."""


@dataclass(frozen=True, slots=True)
class CompletedRun:
    run_id: str
    repetition: int
    bundle: Path
    public_accepted: bool
    simulation_outcome: str
    attempt_count: int


@dataclass(frozen=True, slots=True)
class EvaluationRunSummary:
    experiment_id: str
    runs: tuple[CompletedRun, ...]

    @property
    def passed(self) -> int:
        return sum(
            run.public_accepted and run.simulation_outcome == "passed"
            for run in self.runs
        )


class ProgressReporter:
    """Low-noise console progress with a run-relative monotonic timestamp."""

    def __init__(
        self,
        output: Callable[[str], None] = print,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._output = output
        self._clock = clock
        self._origin = clock()
        self._lock = threading.Lock()

    def emit(self, message: str) -> None:
        elapsed = max(0, round(self._clock() - self._origin))
        minutes, seconds = divmod(elapsed, 60)
        with self._lock:
            self._output(f"[rb {minutes:02d}:{seconds:02d}] {message}")


def _format_byte_count(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KiB"
    return f"{value / (1024 * 1024):.1f} MiB"


def _attempt_status(
    evidence_root: Path,
    workspace: Path,
    attempt_number: int,
    *,
    clock: Callable[[], float] = time.time,
    max_event_bytes: int = 8 * 1024 * 1024,
    max_workspace_entries: int = 10_000,
) -> str:
    """Summarize bounded evaluator evidence without emitting model content."""

    event_path = evidence_root / f"codex-attempt-{attempt_number:03d}.jsonl"
    stderr_path = evidence_root / f"codex-attempt-{attempt_number:03d}.stderr.txt"
    event_count = 0
    tool_count = 0
    error_count = 0
    latest = "awaiting first event"
    truncated = False
    latest_age: int | None = None
    try:
        event_stat = event_path.stat()
        latest_age = max(0, round(clock() - event_stat.st_mtime))
        with event_path.open("r", encoding="utf-8", errors="replace") as stream:
            while stream.tell() < max_event_bytes:
                line = stream.readline()
                if not line:
                    break
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, Mapping):
                    continue
                event_count += 1
                event_type = event.get("type")
                item = event.get("item")
                item_type = item.get("type") if isinstance(item, Mapping) else None
                item_status = item.get("status") if isinstance(item, Mapping) else None
                latest = str(event_type or "unknown")
                if item_type:
                    latest += f"/{item_type}"
                if item_status:
                    latest += f":{item_status}"
                if event_type == "item.completed" and item_type == "command_execution":
                    tool_count += 1
                if event_type == "error":
                    error_count += 1
        truncated = event_stat.st_size > max_event_bytes
    except OSError:
        pass

    file_count = 0
    workspace_bytes = 0
    workspace_truncated = False
    try:
        for current_root, directory_names, file_names in os.walk(
            workspace, followlinks=False
        ):
            directory_names[:] = [
                name
                for name in directory_names
                if not (Path(current_root) / name).is_symlink()
            ]
            for name in file_names:
                path = Path(current_root) / name
                if path.is_symlink() or not path.is_file():
                    continue
                file_count += 1
                try:
                    workspace_bytes += path.stat().st_size
                except OSError:
                    pass
                if file_count >= max_workspace_entries:
                    workspace_truncated = True
                    break
            if workspace_truncated:
                break
    except OSError:
        pass
    try:
        stderr_bytes = stderr_path.stat().st_size
    except OSError:
        stderr_bytes = 0

    event_suffix = "+" if truncated else ""
    file_suffix = "+" if workspace_truncated else ""
    age = f", last event {latest_age}s ago" if latest_age is not None else ""
    return (
        f"check: {event_count}{event_suffix} events, latest {latest}{age}; "
        f"{tool_count} tool command(s) completed, {error_count} error event(s); "
        f"workspace {file_count}{file_suffix} file(s)/{_format_byte_count(workspace_bytes)}; "
        f"stderr {_format_byte_count(stderr_bytes)}"
    )


def _interactive_check_loop(
    input_stream: Any,
    stop: threading.Event,
    callback: Callable[[], None],
    ready: threading.Event | None = None,
) -> None:
    """Watch a real terminal for a single `c` key without consuming line input."""

    if os.name == "nt":  # pragma: no cover - exercised on Windows hardware.
        try:
            import msvcrt

            if ready is not None:
                ready.set()
            while not stop.wait(0.1):
                if msvcrt.kbhit() and msvcrt.getwch().casefold() == "c":
                    callback()
        except (OSError, RuntimeError):
            return
        return

    try:
        import termios
        import tty

        descriptor = input_stream.fileno()
        previous = termios.tcgetattr(descriptor)
        tty.setcbreak(descriptor)
    except (AttributeError, OSError, termios.error):
        return
    if ready is not None:
        ready.set()
    try:
        while not stop.is_set():
            ready, _, _ = select.select((descriptor,), (), (), 0.1)
            if not ready:
                continue
            value = os.read(descriptor, 1)
            if value.lower() == b"c":
                callback()
    except (OSError, ValueError):
        return
    finally:
        try:
            termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)
        except (OSError, termios.error):
            pass


class _AttemptProgress:
    def __init__(
        self,
        executor: Callable[
            [int, Mapping[str, Any] | None, InvocationAdmission],
            HarnessAttemptResult,
        ],
        reporter: ProgressReporter,
        *,
        repetition: int,
        repetitions: int,
        attempts: int,
        remaining: Callable[[], float],
        heartbeat_seconds: float = 60.0,
        input_stream: Any | None = None,
        status_provider: Callable[[int], str] | None = None,
    ) -> None:
        self._executor = executor
        self._reporter = reporter
        self._run_label = f"Run {repetition}/{repetitions}"
        self._attempts = attempts
        self._remaining = remaining
        self._heartbeat_seconds = heartbeat_seconds
        self._input_stream = input_stream
        self._status_provider = status_provider

    def __call__(
        self,
        attempt_number: int,
        feedback: Mapping[str, Any] | None,
        admission: InvocationAdmission,
    ) -> HarnessAttemptResult:
        kind = "repair" if feedback is not None else "initial"
        self._reporter.emit(
            f"{self._run_label}: starting {kind} model attempt "
            f"{attempt_number}/{self._attempts} "
            f"({max(0, round(self._remaining()))}s agent budget remaining)"
        )
        stop = threading.Event()

        def heartbeat() -> None:
            while not stop.wait(self._heartbeat_seconds):
                self._reporter.emit(
                    f"{self._run_label}: model attempt {attempt_number} still running "
                    f"({max(0, round(self._remaining()))}s remaining)"
                )

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        check_thread: threading.Thread | None = None
        if (
            self._input_stream is not None
            and self._status_provider is not None
            and getattr(self._input_stream, "isatty", lambda: False)()
        ):
            check_ready = threading.Event()
            check_thread = threading.Thread(
                target=_interactive_check_loop,
                args=(
                    self._input_stream,
                    stop,
                    lambda: self._reporter.emit(
                        f"{self._run_label}: {self._status_provider(attempt_number)}"
                    ),
                    check_ready,
                ),
                daemon=True,
            )
            check_thread.start()
            if check_ready.wait(timeout=0.2):
                self._reporter.emit(
                    f"{self._run_label}: press c to check local progress; Ctrl-C cancels"
                )
        started = time.monotonic()
        try:
            result = self._executor(attempt_number, feedback, admission)
        except Exception:
            self._reporter.emit(
                f"{self._run_label}: model attempt {attempt_number} ended with an execution error"
            )
            raise
        finally:
            stop.set()
            thread.join(timeout=0.2)
            if check_thread is not None:
                check_thread.join(timeout=0.3)
        self._reporter.emit(
            f"{self._run_label}: model attempt {attempt_number} finished "
            f"in {time.monotonic() - started:.1f}s ({result.terminal_reason})"
        )
        return result


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _challenge_source(project_root: Path) -> Path:
    source = project_root / "challenges" / "busy-intersection" / "v1" / "public"
    if not source.is_dir():
        raise ConductorError(f"Busy Intersection public pack is missing: {source}")
    return source


def _codex_binary(experiment: Experiment) -> Path:
    requested = experiment.client_options.executable or "codex"
    resolved = shutil.which(requested) if not Path(requested).is_absolute() else requested
    if not resolved:
        raise ConductorError(f"Codex executable was not found: {requested}")
    path = Path(resolved).resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ConductorError(f"Codex executable is not a regular executable: {path}")
    return path


def _auth_json() -> Path:
    codex_home_value = os.environ.get("CODEX_HOME")
    codex_home = Path(codex_home_value) if codex_home_value else Path.home() / ".codex"
    auth = codex_home / "auth.json"
    if not auth.is_file() or auth.is_symlink():
        raise ConductorError(
            "Codex file-backed ChatGPT authentication was not found; run `codex login`"
        )
    return auth.resolve()


def _safe_host_environment() -> dict[str, str]:
    keys = ("LANG", "LC_ALL", "LC_CTYPE", "NO_COLOR", "TERM", "TZ")
    return {key: os.environ[key] for key in keys if key in os.environ}


def _native_process_environment(
    *, scoped_home: Path, auth_json: Path
) -> dict[str, str]:
    """Build the portable P0 child environment with one explicit auth exception.

    The actual Codex home is intentionally visible to the Codex parent so it
    can reuse the operator's ChatGPT login.  Native workspace-write sandboxing
    does not prove that model-generated tools cannot read it, so the run is
    recorded as L0/unsealed rather than overstating the protection.
    """

    environment = build_process_environment(
        os.environ,
        scoped_home=scoped_home,
        allowlist=("LANG", "LC_ALL", "LC_CTYPE", "NO_COLOR", "PATH", "TERM", "TZ"),
    )
    environment["CODEX_HOME"] = str(auth_json.parent)
    return environment


def _experiment_id(experiment: Experiment) -> str:
    encoded = json.dumps(
        experiment_to_dict(experiment),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "exp-" + hashlib.sha256(encoded).hexdigest()[:16]


def _public_check(
    path: Path,
    reporter: ProgressReporter,
    *,
    label: str,
) -> PublicCheckResult:
    result = check_static_candidate(path)
    reporter.emit(
        f"{label}: public artifact checks " + ("passed" if result.passed else "failed")
    )
    failed = [item for item in result.checks if item["result"] == "fail"]
    feedback = {
        "summary": (
            "All public artifact checks passed."
            if not failed
            else "Repair every failed public artifact check."
        ),
        "checks": [dict(item) for item in result.checks],
    }
    return PublicCheckResult(
        result.passed,
        feedback,
        tuple(str(item["id"]) for item in result.checks),
    )


def _prompt_builder(base_prompt: str) -> tuple[
    Callable[[int, Mapping[str, Any] | None], str],
    dict[int, str],
    dict[int, Mapping[str, Any] | None],
]:
    prompts: dict[int, str] = {}
    feedbacks: dict[int, Mapping[str, Any] | None] = {}

    def build(attempt: int, feedback: Mapping[str, Any] | None) -> str:
        text = (
            base_prompt.rstrip()
            + "\n\nWork only in /workspace. Public challenge files are available "
            "read-only at /public-challenge. Put the complete final static "
            "submission directly in /workspace, including index.html.\n"
        )
        if feedback is not None:
            text += (
                "\nThis is the single evaluator-controlled repair pass. Fix the "
                "existing workspace in place using this public-check feedback:\n"
                + json.dumps(dict(feedback), ensure_ascii=False, sort_keys=True, indent=2)
                + "\n"
            )
        prompts[attempt] = text
        feedbacks[attempt] = None if feedback is None else dict(feedback)
        return text

    return build, prompts, feedbacks


def _usage(raw_root: Path) -> dict[str, Any]:
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "reasoning_tokens": 0,
        "cache_read_tokens": 0,
        "turns": 0,
    }
    summaries = 0
    for path in sorted(raw_root.glob("codex-attempt-*.summary.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        usage = value.get("usage", {}) if isinstance(value, dict) else {}
        if not isinstance(usage, dict):
            continue
        for key in totals:
            if key == "turns":
                continue
            raw = usage.get(key, 0)
            if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
                totals[key] += raw
        turns = value.get("turns", 0)
        if isinstance(turns, int) and not isinstance(turns, bool) and turns >= 0:
            totals["turns"] += turns
        summaries += 1
    totals["attempt_summaries"] = summaries
    totals["provenance"] = "harness_reported"
    return totals


def _browser_refs(value: object, raw_path: str) -> object:
    """Make evaluator-local identifiers resolve through preserved raw evidence."""

    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, child in value.items():
            if key in {"evidence_ref", "evidence_refs"}:
                refs = child if isinstance(child, list) else [child]
                mapped = [
                    f"{raw_path}#{str(item)}"
                    for item in refs
                    if isinstance(item, str) and item
                ]
                result[key] = mapped if isinstance(child, list) else (mapped[0] if mapped else None)
            else:
                result[key] = _browser_refs(child, raw_path)
        return result
    if isinstance(value, list):
        return [_browser_refs(item, raw_path) for item in value]
    return value


def _sut_provenance(sut: ResolvedSUT) -> dict[str, Any]:
    return {
        "schema_version": "sut-resolution/v1",
        "harness_id": sut.harness_id,
        "provider_id": sut.provider_id,
        "model_adapter_id": sut.model_id,
        "requested_model": sut.model_binding.provider_model_id,
        "canonical_model": sut.model_binding.canonical_id,
        "capabilities": list(sut.capabilities),
        "warnings": list(sut.warnings),
        "adapter_versions": {
            "harness": sut.harness_descriptor.version,
            "provider": sut.provider_descriptor.version,
            "model": sut.model_descriptor.version,
        },
    }


def _execute_one(
    *,
    experiment: Experiment,
    experiment_id: str,
    sut: ResolvedSUT,
    registry: AdapterRegistry,
    run_id: str,
    repetition: int,
    reporter: ProgressReporter,
    project_root: Path,
    inbox: Path,
    temporary_root: Path,
    codex_binary: Path,
    auth_json: Path,
    secret_values: tuple[str, ...],
    chromium: Path,
    playwright_browsers_path: Path,
    input_stream: Any | None,
) -> CompletedRun:
    run_label = f"Run {repetition}/{experiment.repetitions}"
    seed = balanced_seed_for_repetition(repetition)
    reporter.emit(f"{run_label}: preparing isolated workspace")
    public_source = _challenge_source(project_root)
    staged = StagedWorkspace.create(
        base_root=temporary_root,
        run_id=run_id,
        public_challenge_source=public_source,
        forbidden_roots=(project_root, inbox),
    )
    recorder = EventRecorder()
    recorder.record(
        phase="conductor",
        event_type="run.started",
        source="conductor",
        payload={"run_id": run_id, "repetition": repetition},
    )
    raw_root = staged.conductor_root / "raw"
    raw_root.mkdir()
    attempt_store = AttemptStore(staged.conductor_root / "attempts")
    harness = registry.get("harness", experiment.client)
    native_plan = harness.plan(
        experiment.model,
        experiment.client_options.reasoning_effort,
        "workspace-write",
        str(staged.workspace),
        str(codex_binary),
    )
    native_environment = _native_process_environment(
        scoped_home=staged.scoped_home,
        auth_json=auth_json,
    )
    isolation = build_isolation_report(
        environment=native_environment,
        credential_canary=CanaryStatus.NOT_RUN,
        agent_network=NetworkCapability.UNKNOWN,
    )
    reporter.emit(f"{run_label}: staged workspace ready (L0 best-effort protection)")

    plan = InvocationPlan(
        argv=native_plan.argv,
        environment_keys=tuple(sorted(native_environment)),
        model=experiment.model,
        sandbox=native_plan.sandbox,
        working_directory=str(staged.workspace),
        stdin_mode="prompt",
        prompt_argument="-",
    )
    base_prompt = (staged.public_challenge / "prompt.txt").read_text(encoding="utf-8")
    prompt_fn, attempt_prompts, attempt_feedback = _prompt_builder(base_prompt)
    deadline = time.monotonic() + experiment.budget.max_wall_seconds
    remaining = lambda: max(0.0, deadline - time.monotonic())
    codex_executor = CodexAttemptExecutor(
        plan=plan,
        workspace=staged.workspace,
        evidence_root=raw_root,
        prompt=prompt_fn,
        environment=native_environment,
        timeout_seconds=remaining,
        secret_values=secret_values,
    )
    executor = _AttemptProgress(
        codex_executor,
        reporter,
        repetition=repetition,
        repetitions=experiment.repetitions,
        attempts=experiment.budget.max_attempts,
        remaining=remaining,
        input_stream=input_stream,
        status_provider=lambda attempt_number: _attempt_status(
            raw_root, staged.workspace, attempt_number
        ),
    )
    loop = ControlledAttemptLoop(
        executor=executor,
        public_checker=lambda path: _public_check(
            path, reporter, label=run_label
        ),
        attempt_store=attempt_store,
        recorder=recorder,
        max_attempts=experiment.budget.max_attempts,
    )
    loop_started = time.monotonic()
    loop_result = loop.run()
    agent_wall = time.monotonic() - loop_started

    candidate = loop_result.selected_candidate_path
    if candidate is None:
        candidate = staged.conductor_root / "empty-submission"
        candidate.mkdir()
        (candidate / "README.txt").write_text(
            "The harness did not produce a preservable candidate.\n", encoding="utf-8"
        )
    artifact_hash = candidate_tree_hash(candidate)

    reporter.emit(f"{run_label}: monitoring gate completions and recording the overview")
    browser_output = staged.conductor_root / "browser"
    browser = run_browser_evaluation(
        candidate,
        browser_output,
        raw_evidence=raw_root,
        timeout_seconds=90,
        seed=seed,
        chromium=chromium,
        playwright_browsers_path=playwright_browsers_path,
    )
    raw_browser = raw_root / "browser-evaluation.json"
    shutil.copyfile(browser.result_path, raw_browser)
    browser_ref = "events/raw/browser-evaluation.json"
    evaluation = browser.result["evaluation"]
    if not isinstance(evaluation, dict):
        staged.cleanup()
        raise ConductorError("browser worker returned malformed evaluation evidence")
    evaluation = _browser_refs(evaluation, browser_ref)
    assert isinstance(evaluation, dict)
    recorder.record(
        phase="private_evaluation",
        event_type="gate_evaluation.completed",
        source="browser-worker",
        payload={
            "outcome": evaluation.get("outcome"),
            "artifact_hash": artifact_hash,
            "wall_seconds": round(browser.wall_seconds, 6),
        },
    )

    usage = _usage(raw_root)
    raw_refs = tuple(
        sorted(
            {
                reference
                for attempt in loop_result.attempts
                for reference in attempt.raw_evidence_refs
                if reference.startswith("events/raw/")
                and (raw_root / reference.removeprefix("events/raw/")).is_file()
            }
        )
    )
    cost = CostEvidence.subscription_unmetered(
        requested_model=experiment.model,
        evidence_references=raw_refs,
    )
    attempts: list[AttemptBundleEvidence] = []
    for record in loop_result.attempts:
        check = record.public_check
        checks = (
            {
                "passed": False,
                "status": "unavailable",
                "checks": [],
            }
            if check is None
            else {
                "passed": check.passed,
                "status": "complete",
                "assertion_ids": list(check.assertion_ids),
                **dict(check.feedback),
            }
        )
        attempts.append(
            AttemptBundleEvidence(
                record.attempt_number,
                {
                    "schema_version": "attempt/v1",
                    "attempt_number": record.attempt_number,
                    "terminal_reason": record.terminal_reason,
                    "invocation_started": record.invocation_started,
                    "generation_started_evidence": record.invocation_evidence_ref,
                    "candidate_tree_hash": record.candidate_tree_hash,
                    "raw_evidence_refs": list(record.raw_evidence_refs),
                    "failure": (
                        None
                        if record.failure is None
                        else {
                            "stage": record.failure.stage,
                            "error_type": record.failure.error_type,
                        }
                    ),
                },
                attempt_prompts.get(record.attempt_number, base_prompt),
                checks,
                attempt_feedback.get(record.attempt_number),
                record.candidate_path,
            )
        )

    scenario = build_balanced_gate_scenario(seed)
    challenge = json.loads(
        (staged.public_challenge / "challenge.json").read_text(encoding="utf-8")
    )
    challenge.update(
        {
            "scenario_pack": experiment.evaluation.scenario_pack,
            "scenario": scenario.to_dict(),
            "seed": seed,
        }
    )
    capture_metadata = json.loads(
        browser.overview_metadata.read_text(encoding="utf-8")
    )
    capture_metadata.update(
        {
            "artifact_hash": artifact_hash,
            "challenge": experiment.challenge,
            "evidence_refs": [browser_ref],
        }
    )
    simulation_outcome = str(evaluation.get("outcome", "failed"))
    overall_passed = loop_result.accepted and simulation_outcome == "passed"
    created = datetime.now(timezone.utc).isoformat()
    run_manifest = {
        "schema_version": "run/v1",
        "required_features": [],
        "run_id": run_id,
        "experiment_id": experiment_id,
        "repetition": repetition,
        "seed": seed,
        "created_at": created,
        "challenge": experiment.challenge,
        "scenario_pack": experiment.evaluation.scenario_pack,
        "scenario_id": scenario.scenario_id,
        "scenario_profile": scenario.profile,
        "outcome": "passed" if overall_passed else "failed",
        "public_accepted": loop_result.accepted,
        "simulation_outcome": simulation_outcome,
        "measurement_status": evaluation.get("measurement_status", "unmeasurable"),
        "terminal_reason": (
            loop_result.attempts[-1].terminal_reason
            if loop_result.attempts
            else "no-attempt"
        ),
        "attempt_count": len(loop_result.attempts),
        "chargeable_attempt_units": loop_result.chargeable_attempt_units,
        "selected_candidate_hash": artifact_hash,
        "isolation_level": isolation.level.value,
        "sut": {
            "harness": sut.harness_id,
            "provider": sut.provider_id,
            "model_adapter": sut.model_id,
            "requested_model": experiment.model,
        },
    }
    metrics = {
        "schema_version": "metrics/v1",
        "public_accepted": loop_result.accepted,
        "simulation": evaluation.get("metrics", {}),
        "recovery": evaluation.get("recovery", {}),
        "agent": {
            "wall_seconds": round(agent_wall, 6),
            "attempts": len(loop_result.attempts),
            "chargeable_attempt_units": loop_result.chargeable_attempt_units,
            "usage": usage,
        },
        "browser": {"wall_seconds": round(browser.wall_seconds, 6)},
        "evidence_refs": [browser_ref],
    }
    provenance = {
        "environment": {
            "schema_version": "environment/v1",
            "platform": sys.platform,
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "environment_keys": list(plan.environment_keys),
        },
        "redaction": {
            "schema_version": "redaction/v1",
            "status": "applied",
            "credential_contents_archived": False,
            "host_paths_redacted": True,
            "raw_vendor_streams_redacted": True,
            "methods": ["known-credential-exact-match", "credential-patterns"],
        },
        "configuration": {
            "schema_version": "configuration/v1",
            "requested": experiment_to_dict(experiment),
            "effective": {
                "harness": "codex exec",
                "reasoning_effort": experiment.client_options.reasoning_effort,
                "sandbox": native_plan.sandbox,
                "working_directory": "/workspace",
                "public_challenge_delivery": "prompt plus staged read-only copy",
            },
            "cleanup": {
                "planned": True,
                "strategy": "owned staged roots with TemporaryDirectory fallback",
            },
        },
        "sut-resolution": _sut_provenance(sut),
        "isolation": isolation.to_metadata(),
    }
    recorder.record(
        phase="bundle",
        event_type="bundle.finalizing",
        source="conductor",
        payload={"run_id": run_id},
    )
    bundle_evidence = RunBundleEvidence(
        run_manifest=run_manifest,
        experiment=experiment_to_dict(experiment),
        challenge=challenge,
        prompt=attempt_prompts.get(1, base_prompt),
        metrics=metrics,
        cost=cost,
        failures=evaluation.get("failures", []),
        canonical_events_jsonl=recorder.to_jsonl(),
        assertions={
            "schema_version": "assertions/v1",
            "outcome": simulation_outcome,
            "scenario_id": scenario.scenario_id,
            "scenario_profile": scenario.profile,
            "seed": scenario.seed,
            "assertions": evaluation.get("assertions", []),
        },
        capacity_curve={
            "schema_version": "capacity-curve/v1",
            "scenario_id": scenario.scenario_id,
            "scenario_profile": scenario.profile,
            "seed": scenario.seed,
            "stages": evaluation.get("capacity_curve", []),
        },
        runtime_observations={
            "schema_version": "runtime-observations/v1",
            "observations": evaluation.get("runtime_observations", []),
            "gate_monitor": browser.result.get("monitor", {}),
            "browser": browser.result.get("browser", {}),
            "evidence_refs": [browser_ref],
        },
        overview_video=browser.overview_video,
        overview_poster=browser.overview_poster,
        overview_metadata=capture_metadata,
        artifact=candidate,
        raw_evidence=raw_root,
        attempts=tuple(attempts),
        provenance=provenance,
        dependencies={
            "schema_version": "artifact-dependencies/v1",
            "self_contained": True,
            "network_required": False,
        },
    )
    inbox.mkdir(parents=True, exist_ok=True)
    output = inbox / f"{run_id}.ralph.zip"
    reporter.emit(f"{run_label}: finalizing immutable result bundle")
    finalized = finalize_run_bundle(
        bundle_evidence,
        staging=staged.conductor_root / "bundle-staging",
        output=output,
    )
    staged.cleanup()
    reporter.emit(
        f"{run_label}: bundle saved to {finalized.path} "
        f"({'pass' if overall_passed else 'diagnosable fail'})"
    )
    return CompletedRun(
        run_id,
        repetition,
        finalized.path,
        loop_result.accepted,
        simulation_outcome,
        len(loop_result.attempts),
    )


def execute_experiment(
    experiment: Experiment,
    sut: ResolvedSUT,
    registry: AdapterRegistry,
    *,
    output_fn: Callable[[str], None] = print,
    project_root: Path | None = None,
    input_stream: Any | None = None,
) -> EvaluationRunSummary:
    """Run every repetition and produce one validated bundle per repetition."""

    project_root = (project_root or _project_root()).resolve()
    inbox = Path(experiment.output.inbox)
    if not inbox.is_absolute():
        inbox = project_root / inbox
    inbox = inbox.resolve()
    reporter = ProgressReporter(output_fn)
    experiment_id = _experiment_id(experiment)
    run_ids = expand_repetitions(experiment_id, experiment.repetitions)
    codex_binary = _codex_binary(experiment)
    auth_json = _auth_json()
    secret_values = credential_secret_values(auth_json)
    chromium = find_chromium()
    playwright_browsers_path = find_playwright_browsers_path()
    reporter.emit(
        "Preflight complete: "
        f"{sut.harness_id} × {sut.provider_id} × {experiment.model}; "
        f"{experiment.repetitions} independent run(s), up to "
        f"{experiment.budget.max_attempts} attempt(s) each"
    )
    completed: list[CompletedRun] = []
    with tempfile.TemporaryDirectory(prefix="ralph-bench-") as temporary:
        base = Path(temporary)
        for repetition, run_id in enumerate(run_ids, 1):
            completed.append(
                _execute_one(
                    experiment=experiment,
                    experiment_id=experiment_id,
                    sut=sut,
                    registry=registry,
                    run_id=run_id,
                    repetition=repetition,
                    reporter=reporter,
                    project_root=project_root,
                    inbox=inbox,
                    temporary_root=base,
                    codex_binary=codex_binary,
                    auth_json=auth_json,
                    secret_values=secret_values,
                    chromium=chromium,
                    playwright_browsers_path=playwright_browsers_path,
                    input_stream=sys.stdin if input_stream is None else input_stream,
                )
            )
    summary = EvaluationRunSummary(experiment_id, tuple(completed))
    reporter.emit(
        f"Evaluation complete: {len(summary.runs)} bundle(s), "
        f"{summary.passed} full pass(es)"
    )
    return summary


__all__ = [
    "CompletedRun",
    "ConductorError",
    "EvaluationRunSummary",
    "ProgressReporter",
    "execute_experiment",
]
