"""Safe, injectable execution and evidence normalization for Codex CLI.

The adapter in :mod:`codex` deliberately only builds an invocation plan.  This
module supplies the narrow process boundary needed by the conductor without
making the CLI, bundle writer, or challenge evaluator vendor-aware.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time
from typing import Any, Protocol

from ..execution import HarnessAttemptResult, InvocationAdmission
from .contracts import InvocationPlan


class CodexExecutionError(RuntimeError):
    """Raised when a Codex process cannot be started or its evidence is unsafe."""


@dataclass(frozen=True, slots=True)
class ProcessExecutionResult:
    """Conductor-relevant facts about one completed native process."""

    returncode: int | None
    spawned: bool
    prompt_delivered: bool
    timed_out: bool = False
    termination: str | None = None
    wall_seconds: float | None = None


class ProcessExecutor(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        prompt: str,
        cwd: Path,
        env: Mapping[str, str],
        stdout_path: Path,
        stderr_path: Path,
        timeout_seconds: float,
        on_prompt_delivered: Callable[[], None],
    ) -> ProcessExecutionResult: ...


def _validate_process_paths(cwd: Path, stdout_path: Path, stderr_path: Path) -> None:
    if not cwd.is_dir() or cwd.is_symlink():
        raise CodexExecutionError(f"Codex working directory is not a real directory: {cwd}")
    if stdout_path == stderr_path:
        raise CodexExecutionError("Codex stdout and stderr evidence paths must differ")
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)


class SubprocessExecutor:
    """Run one process with a dedicated session and file-backed output.

    Output is written directly to files rather than held in memory.  On
    timeout, the whole process group is terminated, preserving evidence from
    both the CLI and any child tool processes that exited with it.
    """

    def __init__(
        self,
        *,
        popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
        monotonic: Callable[[], float] = time.monotonic,
        terminate_grace_seconds: float = 2.0,
    ) -> None:
        if terminate_grace_seconds <= 0:
            raise ValueError("terminate_grace_seconds must be positive")
        self._popen = popen_factory
        self._monotonic = monotonic
        self._terminate_grace = terminate_grace_seconds

    def run(
        self,
        argv: Sequence[str],
        *,
        prompt: str,
        cwd: Path,
        env: Mapping[str, str],
        stdout_path: Path,
        stderr_path: Path,
        timeout_seconds: float,
        on_prompt_delivered: Callable[[], None],
    ) -> ProcessExecutionResult:
        if not argv or any(not isinstance(arg, str) or not arg for arg in argv):
            raise CodexExecutionError("process argv must contain non-empty strings")
        if timeout_seconds <= 0:
            raise CodexExecutionError("process timeout must be positive")
        if any(not isinstance(key, str) or not key for key in env):
            raise CodexExecutionError("process environment keys must be non-empty strings")
        if any(not isinstance(value, str) for value in env.values()):
            raise CodexExecutionError("process environment values must be strings")
        _validate_process_paths(cwd, stdout_path, stderr_path)
        start = self._monotonic()
        process: subprocess.Popen[Any] | None = None
        spawned = False
        prompt_delivered = False
        try:
            # ``xb`` makes accidental evidence overwrites fail closed.  The
            # caller owns the paths and can choose a new attempt ID instead.
            with (
                stdout_path.open("xb") as stdout,
                stderr_path.open("xb") as stderr,
                tempfile.TemporaryFile(mode="w+", encoding="utf-8") as prompt_stream,
            ):
                stdout_path.chmod(0o600)
                stderr_path.chmod(0o600)
                # A regular, already-populated stdin file cannot deadlock the
                # conductor when a child refuses to read from a pipe.  It also
                # lets the one attempt deadline cover prompt preparation,
                # process startup, and the model process itself.
                prompt_stream.write(prompt)
                prompt_stream.flush()
                prompt_stream.seek(0)
                process = self._popen(
                    tuple(argv),
                    stdin=prompt_stream,
                    stdout=stdout,
                    stderr=stderr,
                    cwd=os.fspath(cwd),
                    env=dict(env),
                    start_new_session=True,
                    text=True,
                )
                spawned = True
                try:
                    prompt_delivered = True
                    on_prompt_delivered()
                except Exception:
                    # A process that spawned but never received its prompt is
                    # infrastructure evidence, not a chargeable invocation.
                    self._terminate(process)
                    raise
                remaining = timeout_seconds - (self._monotonic() - start)
                if remaining <= 0:
                    self._terminate(process)
                    return ProcessExecutionResult(
                        process.returncode,
                        spawned,
                        prompt_delivered,
                        timed_out=True,
                        termination="timeout_process_group_terminated",
                        wall_seconds=self._monotonic() - start,
                    )
                try:
                    returncode = process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    self._terminate(process)
                    return ProcessExecutionResult(
                        process.returncode,
                        spawned,
                        prompt_delivered,
                        timed_out=True,
                        termination="timeout_process_group_terminated",
                        wall_seconds=self._monotonic() - start,
                    )
                return ProcessExecutionResult(
                    returncode,
                    spawned,
                    prompt_delivered,
                    wall_seconds=self._monotonic() - start,
                )
        except CodexExecutionError:
            raise
        except (OSError, ValueError) as exc:
            if process is not None and spawned:
                self._terminate(process)
            raise CodexExecutionError(f"failed to execute Codex: {type(exc).__name__}") from exc
        except BaseException:
            # Ctrl-C and process-level cancellation must not leave a paid
            # Codex process tree running after the conductor exits.
            if process is not None and spawned:
                self._terminate(process)
            raise

    def _terminate(self, process: subprocess.Popen[Any]) -> None:
        """Terminate the dedicated process group, then force it if needed."""

        try:
            if process.poll() is None:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGTERM)
                else:  # pragma: no cover - Windows CI is not required by P0.
                    process.terminate()
                try:
                    process.wait(timeout=self._terminate_grace)
                except subprocess.TimeoutExpired:
                    if os.name == "posix":
                        os.killpg(process.pid, signal.SIGKILL)
                    else:  # pragma: no cover
                        process.kill()
                    process.wait(timeout=self._terminate_grace)
        except (OSError, subprocess.TimeoutExpired):
            # The parent may have exited while a timeout handler was running.
            # The original timeout/process evidence remains authoritative.
            return


_TOKEN_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
        r"id[_-]?token|auth[_-]?token|token|password|secret)"
        r"\s*[\"']?\s*[:=]\s*[\"']?)[^\"'\s,;}]+"
    ),
    re.compile(r"\b(?:sk|ghp|github_pat|xox[baprs])-[-A-Za-z0-9_]{8,}\b"),
)


def redact_text(value: str, secret_values: Sequence[str] = ()) -> str:
    """Redact known secret values and common credential-shaped text."""

    result = value
    for secret in sorted((item for item in secret_values if item), key=len, reverse=True):
        result = result.replace(secret, "[REDACTED]")
    for pattern in _TOKEN_PATTERNS:
        result = pattern.sub(lambda match: match.group(1) + "[REDACTED]" if match.lastindex else "[REDACTED]", result)
    return result


def credential_secret_values(path: Path, *, max_bytes: int = 4 * 1024 * 1024) -> tuple[str, ...]:
    """Extract only credential-bearing JSON values for exact-match redaction."""

    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
            raise CodexExecutionError("credential redaction source is not a bounded regular file")
        value = json.loads(path.read_text(encoding="utf-8"))
    except CodexExecutionError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexExecutionError("credential redaction source is not valid JSON") from exc

    markers = ("token", "secret", "password", "api_key", "apikey", "cookie", "credential")
    found: set[str] = set()

    def visit(item: object, secret_context: bool = False) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                normalized = str(key).casefold().replace("-", "_")
                visit(child, secret_context or any(marker in normalized for marker in markers))
        elif isinstance(item, list):
            for child in item:
                visit(child, secret_context)
        elif secret_context and isinstance(item, str) and len(item) >= 8:
            found.add(item)

    visit(value)
    return tuple(sorted(found, key=lambda item: (-len(item), item)))


def redact_evidence_file(path: Path, secret_values: Sequence[str] = ()) -> None:
    """Atomically redact a text evidence file before it may enter a bundle."""

    if not path.exists():
        return
    if path.is_symlink() or not path.is_file():
        raise CodexExecutionError("raw evidence path is not a regular file")
    temporary = path.with_name(path.name + ".redacting")
    try:
        with (
            path.open("r", encoding="utf-8", errors="replace") as source,
            temporary.open("x", encoding="utf-8") as destination,
        ):
            for line in source:
                destination.write(redact_text(line, secret_values))
            destination.flush()
            os.fsync(destination.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        number = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, number)


def codex_usage_from_obj(value: Mapping[str, Any]) -> dict[str, int]:
    """Normalize known Codex/legacy usage spellings into one integer shape."""

    def first(*keys: str) -> int:
        for key in keys:
            if key in value and value[key] not in (None, ""):
                return _nonnegative_int(value[key])
        return 0

    input_tokens = first("input_tokens", "prompt_tokens", "input", "prompt")
    output_tokens = first("output_tokens", "completion_tokens", "output", "completion")
    reasoning = first("reasoning_output_tokens", "reasoning_tokens", "reasoning")
    cached = first("cached_input_tokens", "cache_read_input_tokens", "cache_read_tokens", "cached")
    total = first("total_tokens", "total") or input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total,
        "reasoning_tokens": reasoning,
        "cache_read_tokens": cached,
    }


def _usage_objects(event: Any) -> list[Mapping[str, Any]]:
    found: list[Mapping[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            usage = value.get("usage")
            if isinstance(usage, Mapping):
                found.append(usage)
            if any(key in value for key in ("input_tokens", "prompt_tokens", "output_tokens", "completion_tokens", "total_tokens")):
                found.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(event)
    return found


def _session_id(event: Mapping[str, Any]) -> str | None:
    for key in ("session_id", "thread_id", "conversation_id"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for key in ("session", "thread", "conversation"):
        nested = event.get(key)
        if isinstance(nested, Mapping) and (found := _session_id(nested)):
            return found
    return None


def _text_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_text_value(item.get("text", item.get("content", ""))) if isinstance(item, Mapping) else _text_value(item) for item in value)
    return ""


def _event_message(event: Mapping[str, Any]) -> str:
    item = event.get("item")
    if isinstance(item, Mapping):
        item_type = str(item.get("type", item.get("kind", ""))).lower()
        if "agent" in item_type or "assistant" in item_type or item.get("role") == "assistant":
            for key in ("text", "content", "message", "delta"):
                text = _text_value(item.get(key))
                if text:
                    return text
    for key in ("final_message", "result", "message"):
        text = _text_value(event.get(key))
        if text:
            return text
    return ""


@dataclass(frozen=True, slots=True)
class CodexStreamSummary:
    events_seen: int = 0
    malformed_lines: int = 0
    session_id: str | None = None
    usage: Mapping[str, int] = field(default_factory=dict)
    turns: int = 0
    final_message: str = ""
    event_types: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self, *, secret_values: Sequence[str] = ()) -> dict[str, Any]:
        return {
            "schema_version": "codex-summary/v1",
            "events_seen": self.events_seen,
            "malformed_lines": self.malformed_lines,
            "session_id": redact_text(self.session_id or "", secret_values) or None,
            "usage": dict(self.usage),
            "turns": self.turns,
            "final_message": redact_text(self.final_message, secret_values),
            "event_types": list(self.event_types),
            "warnings": [redact_text(item, secret_values) for item in self.warnings],
        }


def parse_codex_jsonl(path: Path, *, secret_values: Sequence[str] = ()) -> CodexStreamSummary:
    """Parse JSONL without copying raw vendor payloads into canonical evidence."""

    if not path.is_file():
        raise CodexExecutionError(f"Codex stdout evidence is missing: {path}")
    events_seen = malformed = turns = 0
    session_id: str | None = None
    final_message = ""
    event_types: list[str] = []
    warnings: list[str] = []
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "reasoning_tokens": 0, "cache_read_tokens": 0}
    last_total = 0
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if not isinstance(event, Mapping):
                malformed += 1
                continue
            events_seen += 1
            event_type = str(event.get("type", event.get("event", ""))).strip().lower()
            if event_type:
                event_types.append(event_type)
            session_id = session_id or _session_id(event)
            message = _event_message(event)
            if message:
                final_message = message
            usage_objects = _usage_objects(event)
            if usage_objects and ("turn" in event_type or "complete" in event_type or "usage" in event_type or "usage" in event):
                usage = codex_usage_from_obj(usage_objects[0])
                current_total = usage["total_tokens"]
                if current_total and last_total and current_total >= last_total:
                    scale = (current_total - last_total) / current_total
                else:
                    scale = 1.0
                for key in ("input_tokens", "output_tokens", "reasoning_tokens", "cache_read_tokens"):
                    totals[key] += round(usage[key] * scale)
                totals["total_tokens"] += round(current_total * scale) if current_total else usage["input_tokens"] + usage["output_tokens"]
                last_total = max(last_total, current_total)
                turns += 1
    if malformed:
        warnings.append(f"ignored {malformed} malformed JSONL line(s)")
    if session_id is not None:
        session_id = redact_text(session_id, secret_values)
    return CodexStreamSummary(events_seen, malformed, session_id, totals, turns, redact_text(final_message, secret_values), tuple(event_types), tuple(warnings))


class CodexAttemptExecutor:
    """Adapt one planned Codex invocation to ``ControlledAttemptLoop``."""

    def __init__(
        self,
        *,
        plan: InvocationPlan,
        workspace: Path,
        evidence_root: Path,
        prompt: str | Callable[[int, Mapping[str, Any] | None], str],
        environment: Mapping[str, str],
        timeout_seconds: float | Callable[[], float],
        runner: ProcessExecutor | None = None,
        secret_values: Sequence[str] = (),
    ) -> None:
        self.plan = plan
        self.workspace = Path(workspace)
        self.evidence_root = Path(evidence_root)
        self.prompt = prompt
        self.environment = dict(environment)
        self.timeout_seconds = timeout_seconds
        self.runner = runner or SubprocessExecutor()
        self.secret_values = tuple(secret_values)

    def __call__(
        self,
        attempt_number: int,
        feedback: Mapping[str, Any] | None,
        admission: InvocationAdmission,
    ) -> HarnessAttemptResult:
        if attempt_number < 1:
            raise CodexExecutionError("attempt number must be positive")
        if not self.workspace.is_dir():
            raise CodexExecutionError(f"Codex workspace is not a directory: {self.workspace}")
        text = self.prompt(attempt_number, feedback) if callable(self.prompt) else self.prompt
        if feedback is not None and not callable(self.prompt):
            text += "\n\nEvaluator feedback (repair the current artifact):\n" + json.dumps(dict(feedback), sort_keys=True, ensure_ascii=False)
        stdout_path = self.evidence_root / f"codex-attempt-{attempt_number:03d}.jsonl"
        stderr_path = self.evidence_root / f"codex-attempt-{attempt_number:03d}.stderr.txt"
        summary_path = self.evidence_root / f"codex-attempt-{attempt_number:03d}.summary.json"
        reference = f"events/raw/{stdout_path.name}"

        def delivered() -> None:
            admission.admit(process_spawned=True, prompt_provided=True, evidence_ref=reference)

        cwd = Path(self.plan.working_directory) if self.plan.working_directory else self.workspace
        timeout = self.timeout_seconds() if callable(self.timeout_seconds) else self.timeout_seconds
        if timeout <= 0:
            raise CodexExecutionError("Codex attempt budget is exhausted before process start")
        try:
            result = self.runner.run(
                self.plan.argv,
                prompt=text,
                cwd=cwd,
                env=self.environment,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                timeout_seconds=timeout,
                on_prompt_delivered=delivered,
            )
        finally:
            # Raw vendor streams are useful forensic evidence, but immutable
            # bundles must never receive the unredacted originals.  This also
            # runs on timeout, cancellation, and runner failure.
            redact_evidence_file(stdout_path, self.secret_values)
            redact_evidence_file(stderr_path, self.secret_values)
        summary = parse_codex_jsonl(stdout_path, secret_values=self.secret_values)
        summary_path.write_text(json.dumps(summary.to_dict(secret_values=self.secret_values), sort_keys=True, indent=2) + "\n", encoding="utf-8")
        summary_path.chmod(0o600)
        refs = (reference, f"events/raw/{stderr_path.name}", f"events/raw/{summary_path.name}")
        if result.timed_out:
            reason = "timeout"
        elif result.returncode not in (0, None):
            reason = f"process_exited_{result.returncode}"
        elif result.returncode is None:
            reason = "process_status_unknown"
        else:
            reason = "process_exited"
        candidate = self.workspace if self.workspace.is_dir() else None
        return HarnessAttemptResult(candidate, reason, refs)


__all__ = [
    "CodexAttemptExecutor",
    "CodexExecutionError",
    "CodexStreamSummary",
    "ProcessExecutionResult",
    "ProcessExecutor",
    "SubprocessExecutor",
    "codex_usage_from_obj",
    "credential_secret_values",
    "parse_codex_jsonl",
    "redact_evidence_file",
    "redact_text",
]
