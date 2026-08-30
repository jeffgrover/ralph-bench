"""Conductor-owned run and controlled-attempt primitives.

The module intentionally knows nothing about Codex, traffic, or ZIP bundles.
Adapters supply execution results; the conductor owns attempt admission,
preservation, public feedback, state, and cleanup evidence.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
from types import MappingProxyType
from typing import Any, Protocol
import uuid

from .events import EventRecorder


class ExecutionError(RuntimeError):
    """Base error for conductor contract violations."""


class StateTransitionError(ExecutionError):
    """Raised for an invalid run state transition."""


class AttemptPreservationError(ExecutionError):
    """Raised when a candidate cannot be preserved safely and immutably."""


class RunState(StrEnum):
    CREATED = "created"
    PREFLIGHT = "preflight"
    READY = "ready"
    RUNNING = "running"
    PUBLIC_CHECK = "public_check"
    FINALIZING = "finalizing"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


TERMINAL_STATES = frozenset(
    {RunState.COMPLETE, RunState.FAILED, RunState.CANCELLED, RunState.TIMED_OUT}
)

_ALLOWED_TRANSITIONS: Mapping[RunState, frozenset[RunState]] = {
    RunState.CREATED: frozenset(
        {RunState.PREFLIGHT, RunState.FAILED, RunState.CANCELLED}
    ),
    RunState.PREFLIGHT: frozenset(
        {RunState.READY, RunState.FAILED, RunState.CANCELLED, RunState.TIMED_OUT}
    ),
    RunState.READY: frozenset(
        {RunState.RUNNING, RunState.FAILED, RunState.CANCELLED, RunState.TIMED_OUT}
    ),
    RunState.RUNNING: frozenset(
        {
            RunState.PUBLIC_CHECK,
            RunState.FINALIZING,
            RunState.FAILED,
            RunState.CANCELLED,
            RunState.TIMED_OUT,
        }
    ),
    RunState.PUBLIC_CHECK: frozenset(
        {
            RunState.RUNNING,
            RunState.FINALIZING,
            RunState.FAILED,
            RunState.CANCELLED,
            RunState.TIMED_OUT,
        }
    ),
    RunState.FINALIZING: TERMINAL_STATES,
    RunState.COMPLETE: frozenset(),
    RunState.FAILED: frozenset(),
    RunState.CANCELLED: frozenset(),
    RunState.TIMED_OUT: frozenset(),
}


@dataclass(frozen=True, slots=True)
class StateTransition:
    previous: RunState
    current: RunState
    reason: str


class RunStateMachine:
    def __init__(self, recorder: EventRecorder | None = None) -> None:
        self._state = RunState.CREATED
        self._history: list[StateTransition] = []
        self._recorder = recorder

    @property
    def state(self) -> RunState:
        return self._state

    @property
    def history(self) -> tuple[StateTransition, ...]:
        return tuple(self._history)

    def transition(self, target: RunState, reason: str) -> StateTransition:
        if target not in _ALLOWED_TRANSITIONS[self._state]:
            raise StateTransitionError(
                f"invalid run transition {self._state.value} -> {target.value}"
            )
        if not reason.strip():
            raise StateTransitionError("state transition reason is required")
        transition = StateTransition(self._state, target, reason)
        self._history.append(transition)
        self._state = target
        if self._recorder is not None:
            self._recorder.record(
                phase="conductor",
                event_type="run.state_changed",
                source="conductor",
                payload={
                    "previous": transition.previous.value,
                    "current": transition.current.value,
                    "reason": transition.reason,
                },
            )
        return transition


def expand_repetitions(
    experiment_id: str,
    repetitions: int,
    id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
) -> tuple[str, ...]:
    """Allocate every run identity before execution and reject collisions."""

    if not experiment_id.strip():
        raise ExecutionError("experiment ID is required")
    if repetitions < 1:
        raise ExecutionError("repetitions must be positive")
    result: list[str] = []
    seen: set[str] = set()
    for _ in range(repetitions):
        run_id = id_factory().strip()
        if not run_id or run_id in seen:
            raise ExecutionError("run ID factory returned an empty or duplicate ID")
        seen.add(run_id)
        result.append(run_id)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class CleanupFailure:
    action: str
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class CleanupReport:
    attempted: tuple[str, ...]
    failures: tuple[CleanupFailure, ...]

    @property
    def succeeded(self) -> bool:
        return not self.failures


class CleanupStack:
    """Small idempotent LIFO cleanup stack that preserves every failure."""

    def __init__(self) -> None:
        self._actions: list[tuple[str, Callable[[], None]]] = []
        self._report: CleanupReport | None = None

    def register(self, name: str, action: Callable[[], None]) -> None:
        if self._report is not None:
            raise ExecutionError("cannot register cleanup after cleanup has run")
        if not name.strip():
            raise ExecutionError("cleanup action name is required")
        self._actions.append((name, action))

    def run(self) -> CleanupReport:
        if self._report is not None:
            return self._report
        attempted: list[str] = []
        failures: list[CleanupFailure] = []
        for name, action in reversed(self._actions):
            attempted.append(name)
            try:
                action()
            except Exception as exc:  # Cleanup must continue through independent actions.
                failures.append(
                    CleanupFailure(name, type(exc).__name__, str(exc) or repr(exc))
                )
        self._report = CleanupReport(tuple(attempted), tuple(failures))
        return self._report


@dataclass(frozen=True, slots=True)
class PublicCheckResult:
    passed: bool
    feedback: Mapping[str, Any] = field(default_factory=dict)
    assertion_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            detached = json.loads(
                json.dumps(
                    self.feedback,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        except (TypeError, ValueError) as exc:
            raise ExecutionError("public feedback must be finite JSON data") from exc
        if not isinstance(detached, dict):
            raise ExecutionError("public feedback must be a JSON object")
        assertions = tuple(self.assertion_ids)
        if any(not item.strip() for item in assertions) or len(set(assertions)) != len(
            assertions
        ):
            raise ExecutionError("public assertion IDs must be non-empty and unique")
        object.__setattr__(self, "feedback", MappingProxyType(detached))
        object.__setattr__(self, "assertion_ids", assertions)


@dataclass(frozen=True, slots=True)
class HarnessAttemptResult:
    candidate_path: Path | None
    terminal_reason: str
    raw_evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.terminal_reason.strip():
            raise ExecutionError("attempt terminal reason is required")
        if self.candidate_path is not None:
            object.__setattr__(self, "candidate_path", Path(self.candidate_path))
        refs = tuple(self.raw_evidence_refs)
        if any(not item.strip() for item in refs):
            raise ExecutionError("raw evidence references must be non-empty")
        object.__setattr__(self, "raw_evidence_refs", refs)


class AttemptExecutor(Protocol):
    def __call__(
        self,
        attempt_number: int,
        feedback: Mapping[str, Any] | None,
        admission: "InvocationAdmission",
    ) -> HarnessAttemptResult: ...


class PublicChecker(Protocol):
    def __call__(self, candidate_path: Path) -> PublicCheckResult: ...


class InvocationAdmission:
    """One-shot conductor gate for the chargeable invocation-start event."""

    def __init__(self, attempt_number: int, recorder: EventRecorder) -> None:
        self._attempt_number = attempt_number
        self._recorder = recorder
        self._started = False
        self._evidence_ref: str | None = None

    @property
    def started(self) -> bool:
        return self._started

    @property
    def evidence_ref(self) -> str | None:
        return self._evidence_ref

    def admit(
        self,
        *,
        process_spawned: bool,
        prompt_provided: bool,
        evidence_ref: str,
    ) -> None:
        if self._started:
            raise ExecutionError("model invocation was already admitted")
        if not process_spawned or not prompt_provided:
            raise ExecutionError(
                "model invocation cannot start before process spawn and prompt delivery"
            )
        if not evidence_ref.strip():
            raise ExecutionError("invocation-start evidence reference is required")
        self._started = True
        self._evidence_ref = evidence_ref
        self._recorder.record(
            phase="agent",
            event_type="model_invocation.started",
            source="conductor",
            attempt=self._attempt_number,
            payload={
                "charge_basis": "conservative_invocation_started",
                "evidence_ref": evidence_ref,
            },
        )


def _iter_candidate_files(root: Path) -> Sequence[Path]:
    files: list[Path] = []
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        for name in directory_names:
            path = current / name
            if path.is_symlink():
                raise AttemptPreservationError(f"candidate contains symlink: {path}")
        for name in file_names:
            path = current / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise AttemptPreservationError(
                    f"candidate contains non-regular file: {path}"
                )
            files.append(path)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def candidate_has_files(root: Path) -> bool:
    """Return whether a harness left at least one regular candidate file."""

    if not root.is_dir() or root.is_symlink():
        return False
    for current_root, _directory_names, file_names in os.walk(
        root, followlinks=False
    ):
        current = Path(current_root)
        for name in file_names:
            try:
                if stat.S_ISREG((current / name).lstat().st_mode):
                    return True
            except OSError:
                continue
    return False


def candidate_tree_hash(root: Path) -> str:
    if not root.is_dir() or root.is_symlink():
        raise AttemptPreservationError("candidate path must be a real directory")
    digest = hashlib.sha256()
    for path in _iter_candidate_files(root):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        size = path.stat().st_size
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(size.to_bytes(8, "big"))
        bytes_read = 0
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                bytes_read += len(chunk)
        if bytes_read != size or path.stat().st_size != size:
            raise AttemptPreservationError("candidate changed while being hashed")
    return digest.hexdigest()


class AttemptStore:
    """Preserve each candidate once in a conductor-owned attempt directory."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def preserve(self, attempt_number: int, candidate_path: Path) -> tuple[Path, str]:
        if attempt_number < 1:
            raise AttemptPreservationError("attempt number must be positive")
        candidate_path = candidate_path.resolve()
        if self._root.resolve() == candidate_path or self._root.resolve().is_relative_to(
            candidate_path
        ):
            raise AttemptPreservationError(
                "attempt store cannot be located inside the candidate tree"
            )
        digest = candidate_tree_hash(candidate_path)
        attempt_root = self._root / f"attempt-{attempt_number:03d}"
        destination = attempt_root / "submission"
        temporary = self._root / f".attempt-{attempt_number:03d}.tmp"
        if attempt_root.exists() or temporary.exists():
            raise AttemptPreservationError("attempt snapshot already exists")
        try:
            temporary.mkdir()
            shutil.copytree(candidate_path, temporary / "submission", symlinks=False)
            os.replace(temporary, attempt_root)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
        if candidate_tree_hash(destination) != digest:
            raise AttemptPreservationError("candidate changed while being preserved")
        return destination, digest


@dataclass(frozen=True, slots=True)
class AttemptFailure:
    stage: str
    error_type: str


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    attempt_number: int
    terminal_reason: str
    invocation_started: bool
    invocation_evidence_ref: str | None
    candidate_path: Path | None
    candidate_tree_hash: str | None
    public_check: PublicCheckResult | None
    raw_evidence_refs: tuple[str, ...]
    failure: AttemptFailure | None = None


@dataclass(frozen=True, slots=True)
class ControlledLoopResult:
    attempts: tuple[AttemptRecord, ...]
    accepted: bool
    selected_candidate_path: Path | None
    selected_candidate_hash: str | None

    @property
    def chargeable_attempt_units(self) -> int:
        return sum(1 for attempt in self.attempts if attempt.invocation_started)


class ControlledAttemptLoop:
    """Execute one attempt plus at most one public-feedback repair attempt."""

    def __init__(
        self,
        *,
        executor: AttemptExecutor,
        public_checker: PublicChecker,
        attempt_store: AttemptStore,
        recorder: EventRecorder,
        max_attempts: int = 2,
    ) -> None:
        if max_attempts not in (1, 2):
            raise ExecutionError("P0 controlled loop allows one or two attempts")
        self._executor = executor
        self._public_checker = public_checker
        self._attempt_store = attempt_store
        self._recorder = recorder
        self._max_attempts = max_attempts

    def run(self) -> ControlledLoopResult:
        records: list[AttemptRecord] = []
        feedback: Mapping[str, Any] | None = None
        selected_path: Path | None = None
        selected_hash: str | None = None
        accepted = False

        for attempt_number in range(1, self._max_attempts + 1):
            admission = InvocationAdmission(attempt_number, self._recorder)
            self._recorder.record(
                phase="agent",
                event_type="attempt.started",
                source="conductor",
                attempt=attempt_number,
                payload={"feedback_provided": feedback is not None},
            )
            try:
                result = self._executor(attempt_number, feedback, admission)
            except Exception as exc:
                failure = AttemptFailure("harness_execution", type(exc).__name__)
                records.append(
                    AttemptRecord(
                        attempt_number=attempt_number,
                        terminal_reason="harness_execution_error",
                        invocation_started=admission.started,
                        invocation_evidence_ref=admission.evidence_ref,
                        candidate_path=None,
                        candidate_tree_hash=None,
                        public_check=None,
                        raw_evidence_refs=(),
                        failure=failure,
                    )
                )
                self._recorder.record(
                    phase="agent",
                    event_type="attempt.failed",
                    source="conductor",
                    attempt=attempt_number,
                    payload={"stage": failure.stage, "error_type": failure.error_type},
                )
                break
            preserved_path: Path | None = None
            tree_hash: str | None = None
            check: PublicCheckResult | None = None
            failure: AttemptFailure | None = None

            if result.candidate_path is not None:
                try:
                    preserved_path, tree_hash = self._attempt_store.preserve(
                        attempt_number, result.candidate_path
                    )
                    selected_path, selected_hash = preserved_path, tree_hash
                except Exception as exc:
                    failure = AttemptFailure("candidate_preservation", type(exc).__name__)
                if preserved_path is not None:
                    try:
                        check = self._public_checker(preserved_path)
                        accepted = check.passed
                    except Exception as exc:
                        failure = AttemptFailure("public_check", type(exc).__name__)

            record = AttemptRecord(
                attempt_number=attempt_number,
                terminal_reason=result.terminal_reason,
                invocation_started=admission.started,
                invocation_evidence_ref=admission.evidence_ref,
                candidate_path=preserved_path,
                candidate_tree_hash=tree_hash,
                public_check=check,
                raw_evidence_refs=result.raw_evidence_refs,
                failure=failure,
            )
            records.append(record)
            self._recorder.record(
                phase="public_check" if check is not None else "agent",
                event_type="attempt.completed",
                source="conductor",
                attempt=attempt_number,
                payload={
                    "candidate_preserved": preserved_path is not None,
                    "public_check_passed": None if check is None else check.passed,
                    "terminal_reason": result.terminal_reason,
                    "failure_stage": None if failure is None else failure.stage,
                    "failure_type": None if failure is None else failure.error_type,
                },
            )

            if (
                accepted
                or check is None
                or failure is not None
                or attempt_number == self._max_attempts
            ):
                break
            feedback = dict(check.feedback)

        return ControlledLoopResult(
            attempts=tuple(records),
            accepted=accepted,
            selected_candidate_path=selected_path,
            selected_candidate_hash=selected_hash,
        )
