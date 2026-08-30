"""Native Pi-wiggum execution and bounded JSONL normalization."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from ..execution import HarnessAttemptResult, InvocationAdmission, candidate_has_files
from .codex_execution import (
    ProcessExecutor,
    SubprocessExecutor,
    redact_evidence_file,
    redact_text,
)
from .contracts import HarnessExecutionContext


class PiExecutionError(RuntimeError):
    """Raised when Pi evidence cannot be safely normalized."""


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_text(item) for item in value)
    if isinstance(value, Mapping):
        if value.get("type") in {"text", "output_text"}:
            return _text(value.get("text", value.get("content", "")))
        return _text(value.get("content", value.get("text", "")))
    return ""


def _assistant_message(event: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if event.get("type") != "message_end":
        return None
    message = event.get("message")
    if not isinstance(message, Mapping) or message.get("role") != "assistant":
        return None
    return message


def _usage(message: Mapping[str, Any]) -> dict[str, int]:
    raw = message.get("usage")
    if not isinstance(raw, Mapping):
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "reasoning_tokens": 0,
            "cache_read_tokens": 0,
        }
    input_tokens = _nonnegative_int(raw.get("input", raw.get("input_tokens")))
    output_tokens = _nonnegative_int(raw.get("output", raw.get("output_tokens")))
    cache_read = _nonnegative_int(raw.get("cacheRead", raw.get("cache_read_tokens")))
    reasoning = _nonnegative_int(
        raw.get("reasoning", raw.get("reasoning_tokens"))
    )
    total = _nonnegative_int(raw.get("total", raw.get("total_tokens")))
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total or input_tokens + output_tokens,
        "reasoning_tokens": reasoning,
        "cache_read_tokens": cache_read,
    }


def _tool_calls(message: Mapping[str, Any]) -> int:
    content = message.get("content")
    if not isinstance(content, list):
        return 0
    return sum(
        1
        for item in content
        if isinstance(item, Mapping)
        and str(item.get("type", "")).replace("_", "").casefold()
        in {"toolcall", "tooluse"}
    )


def _session_id(event: Mapping[str, Any]) -> str | None:
    for key in ("session_id", "sessionId", "conversation_id", "conversationId"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


@dataclass(frozen=True, slots=True)
class PiStreamSummary:
    events_seen: int = 0
    malformed_lines: int = 0
    session_id: str | None = None
    usage: Mapping[str, int] = field(default_factory=dict)
    turns: int = 0
    tool_calls: int = 0
    provider_id: str | None = None
    model_id: str | None = None
    final_message: str = ""
    event_types: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self, *, secret_values: Sequence[str] = ()) -> dict[str, Any]:
        return {
            "schema_version": "pi-summary/v1",
            "events_seen": self.events_seen,
            "malformed_lines": self.malformed_lines,
            "session_id": redact_text(self.session_id or "", secret_values) or None,
            "usage": dict(self.usage),
            "turns": self.turns,
            "tool_calls": self.tool_calls,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "final_message": redact_text(self.final_message, secret_values),
            "event_types": list(self.event_types),
            "warnings": [redact_text(item, secret_values) for item in self.warnings],
        }


def parse_pi_jsonl(
    path: Path, *, secret_values: Sequence[str] = ()
) -> PiStreamSummary:
    """Normalize current Pi JSONL events without copying raw payloads."""

    if not path.is_file():
        raise PiExecutionError(f"Pi stdout evidence is missing: {path}")
    events_seen = malformed = turns = tool_calls = 0
    session_id: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    final_message = ""
    event_types: list[str] = []
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "reasoning_tokens": 0,
        "cache_read_tokens": 0,
    }
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
            event_type = str(event.get("type", "")).strip().casefold()
            if event_type:
                event_types.append(event_type)
            session_id = session_id or _session_id(event)
            message = _assistant_message(event)
            if message is None:
                continue
            turns += 1
            usage = _usage(message)
            for key, value in usage.items():
                totals[key] += value
            tool_calls += _tool_calls(message)
            provider_id = provider_id or (
                str(message["provider"]) if isinstance(message.get("provider"), str) else None
            )
            model_id = model_id or (
                str(message["model"]) if isinstance(message.get("model"), str) else None
            )
            message_text = _text(message.get("content", ""))
            if message_text:
                final_message = message_text
    warnings = () if not malformed else (f"ignored {malformed} malformed JSONL line(s)",)
    return PiStreamSummary(
        events_seen,
        malformed,
        redact_text(session_id or "", secret_values) or None,
        totals,
        turns,
        tool_calls,
        redact_text(provider_id or "", secret_values) or None,
        redact_text(model_id or "", secret_values) or None,
        redact_text(final_message, secret_values),
        tuple(event_types),
        warnings,
    )


class PiAttemptExecutor:
    """Run one native Pi-wiggum invocation for the conductor loop."""

    def __init__(
        self,
        context: HarnessExecutionContext,
        *,
        provider_settings: Mapping[str, Any] | None = None,
        runner: ProcessExecutor | None = None,
    ) -> None:
        self.plan = context.plan
        self.workspace = context.workspace
        self.evidence_root = context.evidence_root
        self.prompt = context.prompt
        self.environment = dict(context.environment)
        self.timeout_seconds = context.timeout_seconds
        self.secret_values = tuple(context.secret_values)
        self.provider_settings = dict(provider_settings or context.metadata.get("provider_settings", {}))
        self.runner = runner or context.runner or SubprocessExecutor()

    def _materialize_provider_config(self) -> None:
        agent_dir = Path(
            self.environment.get(
                "PI_CODING_AGENT_DIR",
                str(self.workspace / ".pi" / "agent"),
            )
        )
        agent_dir.mkdir(parents=True, exist_ok=True)
        provider_name = str(self.provider_settings.get("native_name", "lmstudio"))
        endpoint = str(
            self.provider_settings.get(
                "base_url", "http://127.0.0.1:1234/v1"
            )
        )
        models = {
            "providers": {
                provider_name: {
                    "baseUrl": endpoint,
                    "api": "openai-completions",
                    "apiKey": "lm-studio-local",
                    "compat": {
                        "supportsDeveloperRole": False,
                        "supportsReasoningEffort": False,
                    },
                    "models": [{"id": self.plan.model}],
                }
            }
        }
        settings = {
            "defaultProvider": provider_name,
            "defaultModel": self.plan.model,
        }
        (agent_dir / "models.json").write_text(
            json.dumps(models, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        (agent_dir / "settings.json").write_text(
            json.dumps(settings, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )

    def __call__(
        self,
        attempt_number: int,
        feedback: Mapping[str, Any] | None,
        admission: InvocationAdmission,
    ) -> HarnessAttemptResult:
        if attempt_number < 1:
            raise PiExecutionError("attempt number must be positive")
        if not self.workspace.is_dir():
            raise PiExecutionError(f"Pi workspace is not a directory: {self.workspace}")
        text = self.prompt(attempt_number, feedback) if callable(self.prompt) else self.prompt
        if feedback is not None and not callable(self.prompt):
            text += "\n\nEvaluator feedback (repair the current artifact):\n" + json.dumps(
                dict(feedback), sort_keys=True, ensure_ascii=False
            )
        # `/wiggum` is the installed pi-wiggum prompt-template entrypoint. The
        # native workflow owns its internal planning/implementation loop;
        # Ralph's controlled repair loop remains outside this executor.
        text = "/wiggum " + text
        stdout_path = self.evidence_root / f"pi-wiggum-attempt-{attempt_number:03d}.jsonl"
        stderr_path = self.evidence_root / f"pi-wiggum-attempt-{attempt_number:03d}.stderr.txt"
        summary_path = self.evidence_root / f"pi-wiggum-attempt-{attempt_number:03d}.summary.json"
        reference = f"events/raw/{stdout_path.name}"

        def delivered() -> None:
            admission.admit(
                process_spawned=True,
                prompt_provided=True,
                evidence_ref=reference,
            )

        self._materialize_provider_config()
        timeout = self.timeout_seconds() if callable(self.timeout_seconds) else self.timeout_seconds
        if timeout <= 0:
            raise PiExecutionError("Pi attempt budget is exhausted before process start")
        try:
            result = self.runner.run(
                self.plan.argv,
                prompt=text,
                cwd=Path(self.plan.working_directory) if self.plan.working_directory else self.workspace,
                env=self.environment,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                timeout_seconds=timeout,
                on_prompt_delivered=delivered,
            )
        finally:
            redact_evidence_file(stdout_path, self.secret_values)
            redact_evidence_file(stderr_path, self.secret_values)
        summary = parse_pi_jsonl(stdout_path, secret_values=self.secret_values)
        summary_path.write_text(
            json.dumps(summary.to_dict(secret_values=self.secret_values), sort_keys=True, indent=2)
            + "\n",
            encoding="utf-8",
        )
        summary_path.chmod(0o600)
        if result.timed_out:
            reason = "timeout"
        elif result.returncode not in (0, None):
            reason = f"process_exited_{result.returncode}"
        elif result.returncode is None:
            reason = "process_status_unknown"
        else:
            reason = "process_exited"
        return HarnessAttemptResult(
            self.workspace if candidate_has_files(self.workspace) else None,
            reason,
            (
                reference,
                f"events/raw/{stderr_path.name}",
                f"events/raw/{summary_path.name}",
            ),
        )


__all__ = ["PiAttemptExecutor", "PiExecutionError", "PiStreamSummary", "parse_pi_jsonl"]
